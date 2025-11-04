
import { Kline, Orderbook } from '../types';

const PROXY_URL = 'https://cors.geminiproxy.workers.dev/?';
const BASE_URL = `${PROXY_URL}https://api.bybit.com/v5`;

// Fetches candlestick data from Bybit
export const getKlines = async (symbol: string, interval: string, limit: number = 200): Promise<Kline[]> => {
  try {
    const response = await fetch(
      `${BASE_URL}/market/kline?category=linear&symbol=${symbol}&interval=${interval}&limit=${limit}`
    );

    const data = await response.json();

    if (!response.ok || data.retCode !== 0) {
      throw new Error(`Bybit API Error (Klines): ${data.retMsg || `HTTP status ${response.status}`}`);
    }

    // Bybit returns data in reverse chronological order, so we reverse it back
    // and parse it into our Kline type.
    const parsedKlines = data.result.list.reverse().map((k: string[]) => ({
      time: parseInt(k[0]),
      open: parseFloat(k[1]),
      high: parseFloat(k[2]),
      low: parseFloat(k[3]),
      close: parseFloat(k[4]),
      volume: parseFloat(k[5]),
    }));

    return parsedKlines;

  } catch (error) {
    console.error('Error fetching klines from Bybit:', error);
    throw error;
  }
};

// Fetches order book data from Bybit
export const getOrderbook = async (symbol: string, limit: number = 1): Promise<Orderbook> => {
  try {
    const response = await fetch(
      `${BASE_URL}/market/orderbook?category=linear&symbol=${symbol}&limit=${limit}`
    );
    
    const data = await response.json();

    if (!response.ok || data.retCode !== 0) {
      throw new Error(`Bybit API Error (Orderbook): ${data.retMsg || `HTTP status ${response.status}`}`);
    }
    
    const result = data.result;
    return {
        symbol: result.s,
        bids: result.b,
        asks: result.a,
        timestamp: result.ts,
    };
  } catch (error) {
    console.error(`Error fetching orderbook for ${symbol} from Bybit:`, error);
    // Return a default/empty state to avoid crashing the whole analysis
    return { symbol, bids: [], asks: [], timestamp: Date.now() };
  }
};