import WebSocket from 'ws';
import { config } from '../config.js';
import logger from '../utils/logger.js';

class BybitWebSocket {
    constructor(onNewCandleCallback) {
        this.url = config.bybit.wsUrl;
        this.onNewCandle = onNewCandleCallback;
        this.ws = null;
    }

    connect() {
        this.ws = new WebSocket(this.url);

        this.ws.on('open', () => {
            logger.info("WebSocket connection established.");
            const subscription = { op: "subscribe", args: [`kline.${config.interval}.${config.symbol}`] };
            this.ws.send(JSON.stringify(subscription));
            setInterval(() => this.ws.ping(), 20000); // Keep connection alive
        });

        this.ws.on('message', (data) => {
            const message = JSON.parse(data.toString());
            if (message.topic && message.topic.startsWith('kline')) {
                const candle = message.data[0];
                if (candle.confirm === true) {
                    logger.info(`New confirmed ${config.interval}m candle for ${config.symbol}. Close: ${candle.close}`);
                    this.onNewCandle(); // Trigger the main analysis logic
                }
            }
        });

        this.ws.on('close', () => {
            logger.error("WebSocket connection closed. Attempting to reconnect in 10 seconds...");
            setTimeout(() => this.connect(), 10000);
        });

        this.ws.on('error', (err) => logger.exception(err));
    }
}

export default BybitWebSocket;