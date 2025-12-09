/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN CORE (Market Data Module)
 * ======================================================
 * Fetches and processes market data from Bybit API, handling retries and providing cached data.
 */

import axios from 'axios';
import { Decimal } from 'decimal.js';
import { ConfigManager } from '../config.js'; // Access bot configuration
import { NEON } from '../ui.js'; // For console coloring
import logger from '../logger.js'; // Use configured logger

// --- MARKET DATA SERVICE ──────────────────────────────────────────────────
// Fetches and processes market data from Bybit API, handling retries and providing cached data.
export class MarketData {
    constructor(config, tickCallback) {
        this.config = config;
        this.tickCallback = tickCallback; // Callback function to execute on new data
        this.api = axios.create({
            baseURL: 'https://api.bybit.com/v5/market', // Bybit V5 Market API base URL
            timeout: this.config.api.timeout, // Request timeout from config
            headers: { 'X-BAPI-API-KEY': process.env.BYBIT_API_KEY || '' } // API Key header (signature would be needed for private endpoints)
        });
        this.buffers = { main: [], mtf: [] }; // Stores historical candle data for main and MTF intervals
        this.orderbook = { bids: [], asks: [] }; // Stores current orderbook data
        this.lastPrice = 0; // Last traded price from ticker
        this.latency = 0; // API response latency measurement
        this.dailyData = { h: 0, l: 0, c: 0 }; // Daily candle data (High, Low, Close)
        this.lastFetchTime = 0; // Timestamp of the last successful fetch
    }

    // Fetches data with exponential backoff and retry logic.
    async fetchWithRetry(url, params, retries = this.config.api.retries) {
        for (let attempt = 0; attempt <= retries; attempt++) {
            try {
                const startTime = Date.now();
                const response = await this.api.get(url, { params }); // Make GET request
                this.latency = Date.now() - startTime; // Measure latency
                return response.data; // Return response data
            } catch (error) {
                if (attempt === retries) throw error; // Throw error if max retries reached
                // Calculate delay for exponential backoff
                const delay = Math.pow(this.config.api.backoff_factor, attempt) * 1000;
                logger.warn(`[MarketData] Fetch failed for ${url}: ${error.message}. Retrying in ${delay}ms...`);
                await new Promise(resolve => setTimeout(resolve, delay)); // Wait before retrying
            }
        }
    }

    // Fetches all necessary market data points required for analysis.
    async fetchAll() {
        // If simulation mode is enabled, return mock data.
        if (this.config.simulation.mock_data) {
            // This is a placeholder for mock data. Real simulation would load from a file or generate data.
            return {
                price: 25000.00, // Mock price
                candles: Array(this.config.limit).fill({ t: Date.now(), o: 25000, h: 25010, l: 24990, c: 25005, v: 100 }),
                candlesMTF: Array(100).fill({ t: Date.now(), o: 25000, h: 25010, l: 24990, c: 25005, v: 100 }),
                bids: [{ p: 25000.00, q: 100 }],
                asks: [{ p: 25001.00, q: 100 }],
                daily: { h: 25050.00, l: 24950.00, c: 25000.00 },
                timestamp: Date.now()
            };
        }

        try {
            // Fetch data concurrently using Promise.all for efficiency
            const [tickerRes, klineRes, klineMtfRes, orderbookRes, dailyRes] = await Promise.all([
                this.fetchWithRetry('/tickers', { category: 'linear', symbol: this.config.symbol }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: this.config.symbol, interval: this.config.interval, limit: this.config.limit }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: this.config.symbol, interval: this.config.trend_interval, limit: 100 }),
                this.fetchWithRetry('/orderbook', { category: 'linear', symbol: this.config.symbol, limit: this.config.orderbook.depth }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: this.config.symbol, interval: 'D', limit: 2 }) // Daily data for pivots
            ]);

            // Basic validation for crucial data points
            if (!tickerRes?.result?.list?.[0] || !klineRes?.result?.list || !klineMtfRes?.result?.list || !orderbookRes?.result || !dailyRes?.result?.list?.[1]) {
                throw new Error("Incomplete data received from API. Missing essential results.");
            }

            // Helper to parse candle data, ensuring consistent format and reversing for chronological order
            const parseCandles = (list) => list.reverse().map(c => ({
                t: parseInt(c[0]), // Timestamp (ms)
                o: parseFloat(c[1]), // Open
                h: parseFloat(c[2]), // High
                l: parseFloat(c[3]), // Low
                c: parseFloat(c[4]), // Close
                v: parseFloat(c[5])  // Volume
            }));

            const dailyData = dailyRes.result.list[1]; // Previous day's data (index 1 for the most recent completed day)
            const priceData = tickerRes.result.list[0]; // Latest ticker data

            this.lastPrice = parseFloat(priceData.lastPrice); // Update last traded price
            this.buffers.main = parseCandles(klineRes.result.list); // Main interval candles
            this.buffers.mtf = parseCandles(klineMtfRes.result.list); // Trend interval candles
            // Parse orderbook data
            this.orderbook.bids = orderbookRes.result.b.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) }));
            this.orderbook.asks = orderbookRes.result.a.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) }));
            this.dailyData = { // Store daily OHLC
                h: parseFloat(dailyData[2]),
                l: parseFloat(dailyData[3]),
                c: parseFloat(dailyData[4])
            };
            this.lastFetchTime = Date.now(); // Record time of successful fetch

            return true; // Indicate successful fetch
        } catch (e) {
            logger.warn(`[MarketData] FetchAll failed: ${e.message}`);
            return false; // Indicate fetch failure
        }
    }
    
    // Returns the last fetched data structure, or null if no data has been fetched yet.
    fetchAllData() {
        if (!this.lastFetchTime) return null; // Return null if no data has been fetched yet
        return {
            price: this.lastPrice,
            candles: this.buffers.main,
            candlesMTF: this.buffers.mtf,
            bids: this.orderbook.bids,
            asks: this.orderbook.asks,
            daily: this.dailyData,
            timestamp: this.lastFetchTime
        };
    }

    // Starts the periodic fetching of market data based on the configured loop delay.
    async start() {
        logger.log('cyan', `[MarketData] Starting data fetch for ${this.config.symbol} interval ${this.config.interval} (${this.config.delays.loop}s loop)...`);
        while (true) {
            const success = await this.fetchAll();
            if (success && this.tickCallback) {
                this.tickCallback('kline'); // Trigger processing after successful kline fetch
            }
            // Calculate wait time to maintain consistent loop delay, accounting for fetch time
            const elapsed = Date.now() - this.lastFetchTime;
            const waitTime = Math.max(0, (this.config.delays.loop * 1000) - elapsed);
            await new Promise(resolve => setTimeout(resolve, waitTime));
        }
    }
}