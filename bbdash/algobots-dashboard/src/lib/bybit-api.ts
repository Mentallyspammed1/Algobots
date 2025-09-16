import { z } from 'zod';
import { withCache } from './cache';

// #region Zod Schemas and Types
export const TickerInfoSchema = z.object({
  lastPrice: z.string(),
  highPrice24h: z.string(),
  lowPrice24h: z.string(),
  turnover24h: z.string(),
  volume24h: z.string(),
  price24hPcnt: z.string(),
});
export type TickerInfo = z.infer<typeof TickerInfoSchema>;

export const OrderBookEntrySchema = z.tuple([z.string(), z.string()]);
export type OrderBookEntry = z.infer<typeof OrderBookEntrySchema>;

export const OrderBookSchema = z.object({
  bids: z.array(OrderBookEntrySchema),
  asks: z.array(OrderBookEntrySchema),
  ts: z.string(),
});
export type OrderBook = z.infer<typeof OrderBookSchema>;

export const RecentTradeSchema = z.object({
  execId: z.string(),
  execTime: z.union([z.string(), z.number()]),
  price: z.string(),
  qty: z.string(),
  side: z.enum(['Buy', 'Sell']),
  isBlockTrade: z.boolean().optional(),
});
export type RecentTrade = z.infer<typeof RecentTradeSchema>;

export const KlineEntrySchema = z.object({
    time: z.number(),
    open: z.number(),
    high: z.number(),
    low: z.number(),
    close: z.number(),
    volume: z.number(),
    turnover: z.number(),
});
export type KlineEntry = z.infer<typeof KlineEntrySchema>;

// #endregion

// #region Constants
export const BYBIT_WEBSOCKET_URL = 'wss://stream.bybit.com/v5/public/linear';
export const DEFAULT_REQUEST_TIMEOUT = 10000;
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;
const API_CATEGORY = 'linear';
// #endregion

interface ApiResponse<T> {
  retCode: number;
  retMsg: string;
  result: T;
  time: number;
}

async function fetchWithRetry(
  url: string, 
  options: RequestInit = {}
): Promise<any | null> {
  
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_REQUEST_TIMEOUT);
  
  const fetchOptions: RequestInit = {
    cache: 'no-store',
    signal: options.signal || controller.signal,
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options
  };

  for (let i = 0; i <= MAX_RETRIES; i++) {
    try {
      const response = await fetch(url, fetchOptions);
      clearTimeout(timeoutId);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data = await response.json();
      if (data.retCode !== 0) throw new Error(data.retMsg);
      return data;
    } catch (error) {
      clearTimeout(timeoutId);
      if (i === MAX_RETRIES) {
        console.error(`Failed to fetch from Bybit endpoint ${url} after ${MAX_RETRIES} retries:`, error);
        return null;
      }
      await new Promise(res => setTimeout(res, RETRY_DELAY_MS * Math.pow(2, i)));
    }
  }
  return null;
}

const intervalMap: Record<string, string> = {
  '1m': '1', '5m': '5', '15m': '15', '30m': '30', '1h': '60',
  '2h': '120', '4h': '240', '6h': '360', '12h': '720', '1d': 'D',
  '1w': 'W', '1M': 'M',
};

class BybitAPI {
  private config: { baseUrl: string };

  constructor(config: { baseUrl: string }) {
    this.config = config;
  }

  private async get(endpoint: string, params?: Record<string, any>): Promise<any> {
    const url = new URL(this.config.baseUrl + endpoint);
    if(params) {
        Object.keys(params).forEach(key => url.searchParams.append(key, params[key]));
    }
    
    const cachedFetch = withCache(fetchWithRetry, {
      ttl: endpoint.includes('kline') ? 60000 : 10000,
      getKey: (url: string) => url,
    });
    
    return cachedFetch(url.toString());
  }

  public async fetchHistoricalData(symbol: string, timeframe: string, limit: number = 200): Promise<any> {
    const interval = intervalMap[timeframe] || timeframe;
    return this.get('/v5/market/kline', { category: API_CATEGORY, symbol, interval, limit });
  }

  public async fetchMarketData(symbol: string): Promise<any> {
    return this.get('/v5/market/tickers', { category: API_CATEGORY, symbol });
  }

  public async fetchOrderBook(symbol: string, limit: number = 50): Promise<any> {
    return this.get('/v5/market/orderbook', { category: API_CATEGORY, symbol, limit });
  }

  public async fetchRecentTrades(symbol: string, limit: number = 50): Promise<any> {
    return this.get('/v5/market/recent-trade', { category: API_CATEGORY, symbol, limit });
  }
}

const api = new BybitAPI({ baseUrl: 'https://api.bybit.com' });

export const getTicker = async (symbol: string): Promise<TickerInfo | null> => {
    const data = await api.fetchMarketData(symbol);
    if(data && data.result.list.length > 0) {
      const ticker = data.result.list[0];
      const parsed = TickerInfoSchema.safeParse(ticker);
      if(parsed.success) return parsed.data;
      console.error("Failed to parse TickerInfo:", parsed.error);
    }
    return null;
}

export const getOrderBook = async (symbol: string): Promise<OrderBook | null> => {
    const data = await api.fetchOrderBook(symbol);
    if(data) {
        const parsed = OrderBookSchema.safeParse({ bids: data.result.b, asks: data.result.a, ts: data.result.ts });
        if (parsed.success) return parsed.data;
        console.error("Failed to parse OrderBook:", parsed.error);
    }
    return null;
}

export const getRecentTrades = async (symbol: string, limit: number = 30): Promise<RecentTrade[] | null> => {
    const data = await api.fetchRecentTrades(symbol, limit);
    if(data && data.result.list) {
        const parsed = z.array(RecentTradeSchema).safeParse(data.result.list);
        if (parsed.success) return parsed.data;
        console.error("Failed to parse RecentTrades:", parsed.error);
    }
    return null;
}

export const getKline = async (symbol: string, timeframe: string, limit: number = 200): Promise<KlineEntry[] | null> => {
    const data = await api.fetchHistoricalData(symbol, timeframe, limit);
    if(data && data.result.list) {
      const klineData = data.result.list.map((k: string[]) => ({
        time: parseInt(k[0]), open: parseFloat(k[1]), high: parseFloat(k[2]),
        low: parseFloat(k[3]), close: parseFloat(k[4]), volume: parseFloat(k[5]), turnover: parseFloat(k[6])
      })).reverse();
      const parsed = z.array(KlineEntrySchema).safeParse(klineData);
      if(parsed.success) return parsed.data;
      console.error("Failed to parse Kline data:", parsed.error);
    }
    return null;
}
