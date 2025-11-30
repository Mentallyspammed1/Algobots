const axios = require('axios');
const config = require('../config');
const NEON = require('../utils/colors');

async function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

class EnhancedDataProvider {
    constructor() { this.api = axios.create({ baseURL: 'https://api.bybit.com/v5/market', timeout: config.api.timeout }); }
    async fetchWithRetry(url, params, retries = config.api.retries) {
        for (let attempt = 0; attempt <= retries; attempt++) {
            try { return (await this.api.get(url, { params })).data; }
            catch (error) { if (attempt === retries) throw error; console.warn(NEON.ORANGE(`[WARN] Data Fetch Retry (${url}): ${error.message} (Attempt ${attempt + 1}/${retries + 1})`)); await delay(Math.pow(config.api.backoff_factor, attempt) * 1000); }
        }
    }
    async fetchAll() {
        try {
            const [ticker, kline, klineMTF, ob, daily] = await Promise.all([
                this.fetchWithRetry('/tickers', { category: 'linear', symbol: config.symbol }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: config.interval, limit: config.limit }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: config.trend_interval, limit: 100 }),
                this.fetchWithRetry('/orderbook', { category: 'linear', symbol: config.symbol, limit: config.orderbook.depth }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: 'D', limit: 2 })
            ]);
            const parseC = (list) => list.reverse().map(c => ({ o: parseFloat(c[1]), h: parseFloat(c[2]), l: parseFloat(c[3]), c: parseFloat(c[4]), v: parseFloat(c[5]), t: parseInt(c[0]) }));
            return {
                price: parseFloat(ticker.result.list[0].lastPrice), candles: parseC(kline.result.list), candlesMTF: parseC(klineMTF.result.list),
                bids: ob.result.b.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) })), asks: ob.result.a.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) })),
                daily: { h: parseFloat(daily.result.list[1][2]), l: parseFloat(daily.result.list[1][3]), c: parseFloat(daily.result.list[1][4]) },
                timestamp: Date.now()
            };
        } catch (e) { console.warn(NEON.ORANGE(`[WARN] Data Fetch Fail: ${e.message}`)); return null; }
    }
}

module.exports = { EnhancedDataProvider };
