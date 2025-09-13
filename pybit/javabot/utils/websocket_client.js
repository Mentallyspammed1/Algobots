import WebSocket from 'ws';
import { logger } from '../logger.js';
import { setTimeout } from 'timers/promises';
import chalk from 'chalk';

class WebSocketClient {
    constructor(url) {
        this.ws = null;
        this.url = url;
        this.subscriptions = new Set();
        this.callbacks = {};
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelayBase = 1000;
        this.pingInterval = null;
    }

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

    subscribe(topics, callback) {
        const topicKey = Array.isArray(topics) ? topics.join(',') : topics;
        this.subscriptions.add(topicKey);
        this.callbacks[topicKey] = callback;

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ op: 'subscribe', args: Array.isArray(topics) ? topics : [topics] }));
        }
    }
    
    resubscribe() {
        if (this.subscriptions.size > 0) {
            this.subscriptions.forEach(topicKey => {
                const topics = topicKey.split(',');
                logger.info(`Resubscribing to topics: ${topics.join(', ')}`);
                this.ws.send(JSON.stringify({ op: 'subscribe', args: topics }));
            });
        }
    }

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

    startPing() {
        this.pingInterval = setInterval(() => {
            if (this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ op: 'ping' }));
            }
        }, 20000);
    }

    stopPing() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }
}

export default WebSocketClient;
