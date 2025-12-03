const WebSocket = require('ws');
const config =require('../config');
const NEON = require('../utils/colors');

function connect(onMessageCallback) {
    const ws = new WebSocket('wss://stream.bybit.com/v5/public/spot');

    ws.on('open', () => {
        console.log(NEON.GREEN('Bybit WebSocket connected.'));
        const subscribeMsg = {
            op: 'subscribe',
            args: [`kline.${config.interval}.${config.symbol}`]
        };
        ws.send(JSON.stringify(subscribeMsg));
        console.log(NEON.CYAN(`Subscribed to kline.${config.interval}.${config.symbol}`));
    });

    ws.on('message', (data) => {
        try {
            const msg = JSON.parse(data);
            if (msg.topic && msg.topic.startsWith('kline.')) {
                onMessageCallback(msg);
            }
        } catch (error) {
            console.error(NEON.RED('Error processing WebSocket message:'), error);
        }
    });

    ws.on('ping', () => {
        ws.pong();
    });

    ws.on('close', () => {
        console.log(NEON.YELLOW('Bybit WebSocket disconnected. Reconnecting in 5 seconds...'));
        setTimeout(() => module.exports.connect(onMessageCallback), 5000);
    });

    ws.on('error', (err) => {
        console.error(NEON.RED('Bybit WebSocket error:'), err.message);
        ws.close();
    });
    
    return ws;
}

module.exports = { connect };