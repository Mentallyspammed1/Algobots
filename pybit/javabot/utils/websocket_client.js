import WebSocket from 'ws';
import { logger } from '../logger.js';
import { setTimeout } from 'timers/promises';
import chalk from 'chalk';

/**
 * @class WebSocketClient
 * @description A generic WebSocket client for connecting to a WebSocket server, managing subscriptions,
 * reconnections, and message handling.
 */
class WebSocketClient {
    /**
     * @constructor
     * @description Initializes the WebSocketClient with the server URL.
     * @param {string} url - The WebSocket server URL.
     */
    constructor(url) {
        /** @property {WebSocket|null} ws - The WebSocket instance. */
        this.ws = null;
        /** @property {string} url - The WebSocket server URL. */
        this.url = url;
        /** @property {Set<string>} subscriptions - A set of active subscriptions. */
        this.subscriptions = new Set();
        /** @property {Object.<string, Function>} callbacks - Callbacks associated with topics. */
        this.callbacks = {};
        /** @property {number} reconnectAttempts - Current number of reconnection attempts. */
        this.reconnectAttempts = 0;
        /** @property {number} maxReconnectAttempts - Maximum number of reconnection attempts. */
        this.maxReconnectAttempts = 10;
        /** @property {number} reconnectDelayBase - Base delay in milliseconds for reconnection. */
        this.reconnectDelayBase = 1000;
        /** @property {NodeJS.Timeout|null} pingInterval - Interval timer for sending ping messages. */
        this.pingInterval = null;
    }

    /**
     * @method connect
     * @description Establishes a WebSocket connection to the configured URL.
     * Sets up event listeners for open, message, close, and error events.
     * Handles automatic reconnection and resubscription.
     * @returns {void}
     */
    connect() {
        if (this.ws) {
            this.ws.close();
        }
        this.ws = new WebSocket(this.url);

        this.ws.on('open', () => {
            logger.info(chalk.green('WebSocket connected.'));
            this.reconnectAttempts = 0;
            this.resubscribe();
            this.startPing();
        });

        this.ws.on('message', (data) => {
            try {
                const message = JSON.parse(data);
                if (message.topic && this.callbacks[message.topic]) {
                    this.callbacks[message.topic](message.data);
                } else if (message.op === 'pong') {
                    // Handled by ping interval
                } else {
                     for (const key in this.callbacks) {
                        if (message.type && key.includes(message.type)) {
                            this.callbacks[key](message.data);
                            break;
                        }
                    }
                }
            } catch (e) {
                logger.error(`Error processing WebSocket message: ${e.message}`);
            }
        });

        this.ws.on('close', () => {
            logger.warn('WebSocket disconnected.');
            this.stopPing();
            this.reconnect();
        });

        this.ws.on('error', (err) => {
            logger.error(`WebSocket error: ${err.message}`);
            this.ws.close();
        });
    }

    /**
     * @method subscribe
     * @description Subscribes to one or more WebSocket topics and registers a callback function.
     * If the WebSocket is open, it sends the subscription message immediately.
     * @param {string|Array<string>} topics - A single topic string or an array of topic strings to subscribe to.
     * @param {Function} callback - The callback function to execute when a message for the subscribed topic is received.
     * @returns {void}
     */
    subscribe(topics, callback) {
        const topicKey = Array.isArray(topics) ? topics.join(',') : topics;
        this.subscriptions.add(topicKey);
        this.callbacks[topicKey] = callback;

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ op: 'subscribe', args: Array.isArray(topics) ? topics : [topics] }));
        }
    }
    
    /**
     * @method resubscribe
     * @description Resubscribes to all previously registered topics. Called automatically upon successful reconnection.
     * @returns {void}
     */
    resubscribe() {
        if (this.subscriptions.size > 0) {
            this.subscriptions.forEach(topicKey => {
                const topics = topicKey.split(',');
                logger.info(`Resubscribing to topics: ${topics.join(', ')}`);
                this.ws.send(JSON.stringify({ op: 'subscribe', args: topics }));
            });
        }
    }

    /**
     * @method reconnect
     * @description Attempts to reconnect to the WebSocket server with an exponential backoff delay.
     * Stops attempting after `maxReconnectAttempts`.
     * @returns {void}
     */
    reconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelayBase * Math.pow(2, this.reconnectAttempts);
            logger.info(`Attempting to reconnect in ${delay / 1000}s...`);
            setTimeout(() => this.connect(), delay);
        } else {
            logger.error('Max WebSocket reconnect attempts reached.');
        }
    }

    /**
     * @method startPing
     * @description Starts a periodic ping message to keep the WebSocket connection alive.
     * @returns {void}
     */
    startPing() {
        this.pingInterval = setInterval(() => {
            if (this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ op: 'ping' }));
            }
        }, 20000);
    }

    /**
     * @method stopPing
     * @description Stops the periodic ping message interval.
     * @returns {void}
     */
    stopPing() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }
}

export default WebSocketClient;