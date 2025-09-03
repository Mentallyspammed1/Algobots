import axios from 'axios';
import crypto from 'crypto';
import { logger } from './utils.js';
import chalk from 'chalk';

export default class LiveDataFetcher {
  constructor(apiKey, apiSecret, tradingSymbol) {
    this.apiKey = apiKey;
    this.apiSecret = apiSecret;
    this.tradingSymbol = tradingSymbol;
    this.baseUrl = 'https://api.bybit.com'; // Bybit API base URL
  }

  async fetchCurrentPrice() {
    try {
      logger.info(chalk.blue(`Fetching live price for ${this.tradingSymbol} from Bybit...`));
      const endpoint = '/v5/market/tickers';
      const category = 'linear'; // or 'spot', 'inverse', 'option' depending on your trading pair

      const params = {
        symbol: this.tradingSymbol,
        category: category,
      };

      const response = await axios.get(`${this.baseUrl}${endpoint}`, { params });

      if (response.data && response.data.retCode === 0 && response.data.result.list.length > 0) {
        const ticker = response.data.result.list[0];
        const currentPrice = parseFloat(ticker.lastPrice);
        logger.info(chalk.green(`Successfully fetched live price: ${currentPrice}`));
        return { currentPrice, symbol: this.tradingSymbol };
      } else {
        logger.warn(chalk.yellow(`Failed to fetch live price: ${response.data.retMsg || 'Unknown error'}`));
        return null;
      }
    } catch (error) {
      logger.error(chalk.red(`Error fetching live price from Bybit: ${error.message}`));
      return null;
    }
  }

  async fetchKlineData(interval, limit) {
    try {
      logger.info(chalk.blue(`Fetching ${limit} ${interval}-minute klines for ${this.tradingSymbol} from Bybit...`));
      const endpoint = '/v5/market/kline';
      const category = 'linear';

      const params = {
        symbol: this.tradingSymbol,
        category: category,
        interval: interval,
        limit: limit,
      };

      const response = await axios.get(`${this.baseUrl}${endpoint}`, { params });

      if (response.data && response.data.retCode === 0 && response.data.result.list.length > 0) {
        const klines = response.data.result.list.map(kline => ({
          startTime: parseInt(kline[0]),
          open: parseFloat(kline[1]),
          high: parseFloat(kline[2]),
          low: parseFloat(kline[3]),
          close: parseFloat(kline[4]),
          volume: parseFloat(kline[5]),
          turnover: parseFloat(kline[6]),
        }));
        logger.info(chalk.green(`Successfully fetched ${klines.length} klines.`));
        return klines;
      } else {
        logger.warn(chalk.yellow(`Failed to fetch kline data: ${response.data.retMsg || 'Unknown error'}`));
        return null;
      }
    } catch (error) {
      logger.error(chalk.red(`Error fetching kline data from Bybit: ${error.message}`));
      return null;
    }
  }
}