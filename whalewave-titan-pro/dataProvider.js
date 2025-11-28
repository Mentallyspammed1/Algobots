// dataProvider.js
import axios from 'axios';
import { delay } from 'timers/promises';
import { config } from './config.js';
import chalk from 'chalk';

export class EnhancedDataProvider {
  constructor() {
    this.api = axios.create({
      baseURL: 'https://api.bybit.com/v5/market',
      timeout: config.api.timeout
    });
    this.circuit = {
      failures: 0,
      threshold: 5,
      resetTime: 60000,
      lastSuccess: Date.now()
    };
    this.maxCandles = Math.max(config.limit, 300);
  }

  isCircuitOpen() {
    if (this.circuit.failures >= this.circuit.threshold) {
      if (Date.now() - this.circuit.lastSuccess > this.circuit.resetTime) {
        this.circuit.failures = 0;
        return false;
      }
      return true;
    }
    return false;
  }

  async fetchWithRetry(url, params, retries = config.api.retries) {
    if (this.isCircuitOpen()) throw new Error('Circuit breaker OPEN - too many failures');
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const res = await this.api.get(url, { params });
        this.circuit.failures = 0;
        this.circuit.lastSuccess = Date.now();
        return res.data;
      } catch (e) {
        this.circuit.failures++;
        if (attempt === retries) throw e;
        const backoffMs = Math.pow(config.api.backoff_factor, attempt) * 1000;
        await delay(backoffMs);
      }
    }
  }

  async fetchAll() {
    try {
      const [ticker, kline, klineMTF, ob, daily] = await Promise.all([
        this.fetchWithRetry('/tickers', {
          category: 'linear',
          symbol: config.symbol
        }),
        this.fetchWithRetry('/kline', {
          category: 'linear',
          symbol: config.symbol,
          interval: config.interval,
          limit: this.maxCandles
        }),
        this.fetchWithRetry('/kline', {
          category: 'linear',
          symbol: config.symbol,
          interval: config.trend_interval,
          limit: 100
        }),
        this.fetchWithRetry('/orderbook', {
          category: 'linear',
          symbol: config.symbol,
          limit: config.orderbook.depth
        }),
        this.fetchWithRetry('/kline', {
          category: 'linear',
          symbol: config.symbol,
          interval: 'D',
          limit: 2
        })
      ]);

      if (
        !ticker?.result?.list?.[0] ||
        !kline?.result?.list ||
        !klineMTF?.result?.list
      ) {
        throw new Error('Invalid API response structure');
      }

      const parseC = (list) =>
        list
          .slice()
          .reverse()
          .map(c => ({
            o: parseFloat(c[1]),
            h: parseFloat(c[2]),
            l: parseFloat(c[3]),
            c: parseFloat(c[4]),
            v: parseFloat(c[5]),
            t: parseInt(c[0])
          }))
          .slice(-this.maxCandles);

      return {
        price: parseFloat(ticker.result.list[0].lastPrice),
        candles: parseC(kline.result.list),
        candlesMTF: parseC(klineMTF.result.list),
        bids: (ob.result?.b || []).map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) })),
        asks: (ob.result?.a || []).map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) })),
        daily: daily.result?.list?.[1]
          ? {
              h: parseFloat(daily.result.list[1][2]),
              l: parseFloat(daily.result.list[1][3]),
              c: parseFloat(daily.result.list[1][4])
            }
          : { h: 0, l: 0, c: 0 },
        timestamp: Date.now()
      };
    } catch (e) {
      console.warn(chalk.ORANGE(`[WARN] Data Fetch Fail: ${e.message}`));
      return null;
    }
  }
}
