import axios from 'axios';
import WebSocket from 'ws';
import { COLOR } from '../ui.js';

/**
 * Manages market data streams (historical and live) from Bybit.
 */
export class MarketData {
    constructor(config, leviathanInstance) {
        this.config = config;
        this.leviathanInstance = leviathanInstance; // Store the Leviathan instance
        this.ws = null;
        this.buffers = {
            scalping: [], 
            main: [],     
            trend: []     
        };
        this.lastPrice = 0;
        this.orderbook = { bids: [], asks: [] };
        this.latency = 0;
    }

    async start() {
        await this.loadHistory();
        this.connectWSS();
    }

    async loadHistory() {
        const client = axios.create({ baseURL: 'https://api.bybit.com/v5/market' });
        const loadKline = async (interval, targetBuffer) => {
            try {
                const res = await client.get('/kline', {
                    params: { category: 'linear', symbol: this.config.symbol, interval, limit: 200 }
                });
                if (res.data.retCode === 0) {
                    this.buffers[targetBuffer] = res.data.result.list.map(k => ({
                        startTime: parseInt(k[0]), 
                        open: parseFloat(k[1]), 
                        high: parseFloat(k[2]), 
                        low: parseFloat(k[3]), 
                        close: parseFloat(k[4]), 
                        volume: parseFloat(k[5])
                    })).reverse(); // Bybit sends newest first, we want oldest first
                    console.log(COLOR.GREEN(`[MarketData] Loaded ${interval} klines for buffer: ${targetBuffer}`));
                    // Added logging for loadHistory
                    if (this.buffers[targetBuffer].length > 0) {
                        const lastKline = this.buffers[targetBuffer][this.buffers[targetBuffer].length - 1];
                        console.log(COLOR.CYAN(`[MarketData-History] Buffer: ${targetBuffer}, Last Kline Close: ${lastKline.close}, Length: ${this.buffers[targetBuffer].length}`));
                    } else {
                        console.log(COLOR.YELLOW(`[MarketData-History] Buffer: ${targetBuffer} is empty after loading.`));
                    }
                } else {
                    console.error(COLOR.RED(`[MarketData] Failed loading ${interval} klines: ${res.data.retMsg}`));
                }
            } catch (e) { 
                if (e.response && e.response.status === 403) {
                    console.error(COLOR.RED(`[MarketData] Failed loading ${interval} klines (403 Forbidden): Please check your Bybit API key permissions (read-only access for Market Data is usually sufficient).`));
                } else {
                    console.error(COLOR.RED(`[MarketData] Failed loading ${interval} klines: ${e.message}`)); 
                }
            }
        };

        await Promise.all([
            loadKline(this.config.intervals.scalping, 'scalping'),
            loadKline(this.config.intervals.main, 'main'),
            loadKline(this.config.intervals.trend, 'trend')
        ]);
        console.log(COLOR.CYAN(`[MarketData] Historical data loaded.`));
    }

    connectWSS() {
        this.ws = new WebSocket('wss://stream.bybit.com/v5/public/linear');
        
        this.ws.on('open', () => {
            console.log(COLOR.GREEN(`[WSS] Connected.`));
            const args = [
                `tickers.${this.config.symbol}`,
                `orderbook.50.${this.config.symbol}`,
                `kline.${this.config.intervals.scalping}.${this.config.symbol}`,
                `kline.${this.config.intervals.main}.${this.config.symbol}`
            ];
            this.ws.send(JSON.stringify({ op: 'subscribe', args }));
            this.startHeartbeat();
        });

        this.ws.on('message', (data) => this.handleMessage(data));
        this.ws.on('error', (err) => {
            console.error(COLOR.RED(`[WSS] Error: ${err.message}`));
            this.ws.close();
        });
        this.ws.on('close', () => {
            console.log(COLOR.YELLOW(`[WSS] Disconnected. Reconnecting...`));
            setTimeout(() => this.connectWSS(), this.config.delays.wsReconnect);
        });
    }

    handleMessage(data) {
        const msg = JSON.parse(data);
        
        if (msg.ts) {
            this.latency = Date.now() - msg.ts;
        }

        if (msg.topic?.startsWith('tickers')) {
            this.handleTicker(msg.data);
        } else if (msg.topic?.startsWith('orderbook')) {
            this.handleOrderbook(msg.data);
        } else if (msg.topic?.startsWith('kline')) {
            this.handleKline(msg);
        }
    }

    handleTicker(data) {
        const tickerData = Array.isArray(data) ? data[0] : data;
        if (tickerData?.lastPrice) {
            this.lastPrice = parseFloat(tickerData.lastPrice);
            this.leviathanInstance.onTick('price'); // Direct call
        }
    }

    handleOrderbook(data) {
        const frame = Array.isArray(data) ? data[0] : data;
        this.orderbook = { bids: frame.b || [], asks: frame.a || [] };
        this.leviathanInstance.onTick('orderbook'); // Direct call
    }

    handleKline(msg) {
        const k = msg.data[0];
        const interval = msg.topic.split('.')[1];
        const type = interval === this.config.intervals.scalping ? 'scalping' : 'main';
        
        // Added logging for handleKline
        if (!k || typeof k.close === 'undefined') {
            console.warn(COLOR.RED(`[MarketData-WSS] Received kline data with missing or undefined k.close. Full k: ${JSON.stringify(k)}`));
        } else {
            console.log(COLOR.CYAN(`[MarketData-WSS] Raw k.close: ${k.close}, Parsed candle.close: ${parseFloat(k.close)}`));
        }

        const candle = {
            startTime: parseInt(k.start), 
            open: parseFloat(k.open), 
            high: parseFloat(k.high),
            low: parseFloat(k.low), 
            close: parseFloat(k.close), 
            volume: parseFloat(k.volume)
        };
        
        const buf = this.buffers[type];
        if (buf) {
            if (buf.length > 0 && buf[buf.length - 1].startTime === candle.startTime) {
                buf[buf.length - 1] = candle; // Update last candle
            } else {
                buf.push(candle); // Add new candle
                if (buf.length > this.config.limits.kline) {
                    buf.shift(); // Maintain buffer size
                }
            }
            // Added logging after buffer update
            console.log(COLOR.CYAN(`[MarketData-WSS] Buffer: ${type}, Current Last Kline Close: ${buf[buf.length-1]?.close}, Length: ${buf.length}`));
            this.leviathanInstance.onTick('kline'); // Direct call
        }
    }

    startHeartbeat() {
        if (this.heartbeatInterval) clearInterval(this.heartbeatInterval);
        this.heartbeatInterval = setInterval(() => {
            if (this.ws?.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ op: 'ping' }));
            }
        }, 20000);
    }

    // New method to get kline data
    getKlines(bufferType = 'main') {
        if (this.buffers[bufferType]) {
            return this.buffers[bufferType];
        }
        console.warn(COLOR.YELLOW(`[MarketData] Invalid bufferType requested: ${bufferType}`));
        return [];
    }
}
