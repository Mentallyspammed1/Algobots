import { EventEmitter } from 'events';
import WebSocket from 'ws';
import { config } from '../config.js';
import logger from '../utils/logger.js';
import crypto from 'crypto-js';

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

class BybitWebSocket extends EventEmitter { // Extend EventEmitter
    constructor() { // Remove onNewCandleCallback, onPrivateMessageCallback from constructor
        super(); // Call EventEmitter constructor
        this.publicUrl = config.bybit.testnet ? 'wss://stream-testnet.bybit.com/v5/public/linear' : config.bybit.wsUrl;
        this.privateUrl = config.bybit.testnet ? 'wss://stream-testnet.bybit.com/v5/private' : config.bybit.privateWsUrl;
        this.publicWs = null;
        this.privateWs = null;
        this.apiKey = process.env.BYBIT_API_KEY;
        this.apiSecret = process.env.BYBIT_API_SECRET;
        this.publicPingInterval = null;
        this.privatePingInterval = null;
        this.publicReconnectTimeout = null; // IMPROVEMENT 9: Reconnect timeout management
        this.privateReconnectTimeout = null; // IMPROVEMENT 9: Reconnect timeout management
        this.publicRetryAttempt = 0; // IMPROVEMENT 9: Retry attempt counter
        this.privateRetryAttempt = 0; // IMPROVEMENT 9: Retry attempt counter
        // IMPROVEMENT 7: Track active subscriptions
        this.publicSubscriptions = new Set();
        this.privateSubscriptions = new Set();
    }

    // IMPROVEMENT 9: Centralized WebSocket connection and reconnection logic with backoff
    _connectWs(type, url, onOpen, onMessage, onClose, onError) {
        let ws = new WebSocket(url);
        let retryAttempt = (type === 'public') ? this.publicRetryAttempt : this.privateRetryAttempt;
        let reconnectTimeoutVar = (type === 'public') ? 'publicReconnectTimeout' : 'privateReconnectTimeout';

        ws.on('open', () => {
            logger.info(`${type} WebSocket connection established.`);
            if (type === 'public') this.publicRetryAttempt = 0;
            else this.privateRetryAttempt = 0;
            clearTimeout(this[reconnectTimeoutVar]);
            onOpen(ws);
        });

        ws.on('message', onMessage);

        ws.on('close', () => {
            logger.error(`${type} WebSocket connection closed. Attempting to reconnect with backoff...`);
            this._scheduleReconnect(type, url, onOpen, onMessage, onClose, onError);
        });

        ws.on('error', (err) => {
            logger.exception(`Error on ${type} WebSocket:`, err);
            onError(err);
            // Close the socket to trigger a reconnect if it's not already closing
            if (ws.readyState === WebSocket.OPEN) {
                ws.close();
            }
        });

        return ws;
    }

    _scheduleReconnect(type, url, onOpen, onMessage, onClose, onError) {
        let retryAttempt = (type === 'public') ? this.publicRetryAttempt : this.privateRetryAttempt;
        let reconnectTimeoutVar = (type === 'public') ? 'publicReconnectTimeout' : 'privateReconnectTimeout';

        const delay = Math.min(config.bybit.maxReconnectDelayMs, Math.pow(2, retryAttempt) * 1000); // Exponential backoff
        logger.info(`Scheduling ${type} WebSocket reconnection in ${delay / 1000} seconds (attempt ${retryAttempt + 1})...`);

        this[reconnectTimeoutVar] = setTimeout(() => {
            if (type === 'public') {
                this.publicRetryAttempt++;
                this.publicWs = this._connectWs(type, url, onOpen, onMessage, onClose, onError);
            } else {
                this.privateRetryAttempt++;
                this.privateWs = this._connectWs(type, url, onOpen, onMessage, onClose, onError);
            }
        }, delay);
    }

    // IMPROVEMENT 10: Unified ping/pong management
    _startHeartbeat(ws, intervalVar, pingIntervalMs) { // Pass intervalMs as argument
        clearInterval(this[intervalVar]);
        this[intervalVar] = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.ping();
            }
        }, pingIntervalMs);

        ws.on('pong', () => {
            logger.debug(`Received pong from ${ws.url}`);
        });
    }

    _stopHeartbeat(intervalVar) {
        clearInterval(this[intervalVar]);
        this[intervalVar] = null;
    }

    connectPublic() {
        this.publicWs = this._connectWs('public', this.publicUrl,
            (ws) => {
                const subscription = { op: "subscribe", args: [`kline.${config.primaryInterval}.${config.symbol}`] };
                ws.send(JSON.stringify(subscription));
                logger.info(`Subscribed to public topic: ${subscription.args}`);
                this._startHeartbeat(ws, 'publicPingInterval', config.bybit.publicPingIntervalMs);
            },
            (data) => {
                const message = JSON.parse(data.toString());
                if (message.topic && message.topic.startsWith('kline')) {
                    const candle = message.data[0];
                    if (candle.confirm === true) {
                        logger.debug(`New confirmed ${config.primaryInterval}m candle for ${config.symbol}. Close: ${candle.close}`);
                        this.emit('candle', candle); // Emit a 'candle' event
                    }
                }
            },
            () => this._stopHeartbeat('publicPingInterval'),
            (err) => logger.error("Public WS error:", err)
        );
    }

    // IMPROVEMENT 11: Private WebSocket Authentication and Subscription
    connectPrivate() {
        this.privateWs = this._connectWs('private', this.privateUrl,
            (ws) => {
                const expires = Date.now() + 10000;
                const signature = crypto.HmacSHA256(`GET/realtime${expires}`, this.apiSecret).toString();
                const authMessage = { op: "auth", args: [this.apiKey, expires.toString(), signature] };
                ws.send(JSON.stringify(authMessage));
                logger.info("Sent private WebSocket authentication request.");

                const authHandler = (data) => {
                    const message = JSON.parse(data.toString());
                    if (message.op === 'auth') {
                        if (message.success) {
                            logger.info("Private WebSocket authenticated successfully.");
                            ws.off('message', authHandler);
                            const privateSubscriptions = { op: "subscribe", args: [`order`, `position`] };
                            ws.send(JSON.stringify(privateSubscriptions));
                            logger.info(`Subscribed to private topics: ${privateSubscriptions.args}`);
                            this._startHeartbeat(ws, 'privatePingInterval', config.bybit.privatePingIntervalMs);
                        } else {
                            logger.error(`Private WebSocket authentication failed: ${message.retMsg} (Code: ${message.retCode})`);
                            ws.close();
                        }
                    } else {
                        this.emit('privateMessage', message); // Emit a 'privateMessage' event
                    }
                };
                ws.on('message', authHandler);
            },
            (data) => {
                const message = JSON.parse(data.toString());
                this.emit('privateMessage', message); // Emit a 'privateMessage' event
                // ... existing unhandled message logging ...
            },
    }

    // IMPROVEMENT 11: Private WebSocket Authentication and Subscription
    connectPrivate() {
        this.privateWs = this._connectWs('private', this.privateUrl,
            (ws) => {
                const expires = Date.now() + 10000;
                const signature = crypto.HmacSHA256(`GET/realtime${expires}`, this.apiSecret).toString();
                const authMessage = {
                    op: "auth",
                    args: [this.apiKey, expires.toString(), signature]
                };
                ws.send(JSON.stringify(authMessage));
                logger.info("Sent private WebSocket authentication request.");

                const authHandler = (data) => {
                    const message = JSON.parse(data.toString());
                    if (message.op === 'auth') { // IMPROVEMENT 10: Check for 'auth' operation
                        if (message.success) {
                            logger.info("Private WebSocket authenticated successfully.");
                            ws.off('message', authHandler); // Remove handler after successful auth
                            
                            // IMPROVEMENT 10: Subscribe to topics ONLY after successful authentication
                            const privateSubscriptions = {
                                op: "subscribe",
                                args: [`order`, `position`]
                            };
                            ws.send(JSON.stringify(privateSubscriptions));
                            logger.info(`Subscribed to private topics: ${privateSubscriptions.args}`);
                            this._startHeartbeat(ws, 'privatePingInterval', config.bybit.privatePingIntervalMs);
                        } else {
                            logger.error(`Private WebSocket authentication failed: ${message.retMsg} (Code: ${message.retCode})`);
                            ws.close(); // Close connection on auth failure to trigger reconnect
                            // Optionally throw an error here to propagate the failure
                            // throw new Error(`Private WS Auth Failed: ${message.retMsg}`);
                        }
                    } else {
                        // This else block handles messages that are not 'auth' responses but arrive before auth is complete.
                        // For example, if Bybit sends pings or other messages immediately.
                        // We still pass them to the main handler, but keep authHandler active.
                        this.onPrivateMessage(message); // Pass to main handler
                    }
                };
                ws.on('message', authHandler);
            },
            (data) => {
                const message = JSON.parse(data.toString());
                // IMPROVEMENT 11: Pass all private messages to callback for further processing
                // Add a check to log messages not explicitly handled if desired in the callback
                this.onPrivateMessage(message);

                // Optional: Log messages that don't match known topics if your onPrivateMessage doesn't handle everything
                if (message.topic && !['order', 'position'].includes(message.topic)) {
                    logger.debug(`Unhandled private WS message topic: ${message.topic}`, message);
                } else if (!message.topic && message.op && message.op !== 'auth' && message.type !== 'pong') {
                    logger.debug(`Unhandled private WS message (no topic, op: ${message.op}):`, message);
                }
            },
            () => this._stopHeartbeat('privatePingInterval'),
            (err) => logger.error("Private WS error:", err)
        );
    }

    /**
     * Disconnects both public and private WebSocket connections and cleans up resources.
     * It attempts to gracefully close connections and stop heartbeats.
     */
    disconnect() {
        logger.info("Initiating WebSocket graceful shutdown...");
        this._stopHeartbeat('publicPingInterval');
        this._stopHeartbeat('privatePingInterval');
        clearTimeout(this.publicReconnectTimeout);
        clearTimeout(this.privateReconnectTimeout);

        if (this.publicWs && this.publicWs.readyState === WebSocket.OPEN) {
            this.publicWs.close(1000, 'Shutdown initiated'); // 1000 is Normal Closure
            logger.info("Public WebSocket closing.");
        } else if (this.publicWs) {
            logger.warn("Public WebSocket not open, setting to null.");
            this.publicWs = null;
        }

        if (this.privateWs && this.privateWs.readyState === WebSocket.OPEN) {
            this.privateWs.close(1000, 'Shutdown initiated');
            logger.info("Private WebSocket closing.");
        } else if (this.privateWs) {
            logger.warn("Private WebSocket not open, setting to null.");
            this.privateWs = null;
        }
        logger.info("WebSockets disconnected.");
    }

    connect() {
        this.connectPublic();
        this.connectPrivate();
    }
}

export default BybitWebSocket;