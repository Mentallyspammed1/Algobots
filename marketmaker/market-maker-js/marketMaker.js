require('dotenv').config();
const WebSocket = require('ws');
const { placeOrder, cancelAllOrders, IS_TESTNET } = require('./bybitClient');

// --- Configuration ---
const config = {
    SYMBOL: process.env.SYMBOL || 'BTCUSDT',
    SPREAD: parseFloat(process.env.SPREAD) || 10.0,
    ORDER_QTY: process.env.ORDER_QTY || '0.001',
    REFRESH_MS: parseInt(process.env.REFRESH_MS) || 5000,
    CATEGORY: 'linear',
};

console.log('--- Market Maker Bot Starting ---');
console.log(`Environment: ${IS_TESTNET ? 'Testnet' : 'Mainnet'}`);
console.log('Configuration:', config);
console.log('---------------------------------');


// --- State ---
let bestBid = 0;
let bestAsk = 0;
let isUpdating = false; // Lock to prevent concurrent updates

// --- WebSocket Connection ---
const wsUrl = IS_TESTNET ? 'wss://stream-testnet.bybit.com/v5/public/linear' : 'wss://stream.bybit.com/v5/public/linear';
const ws = new WebSocket(wsUrl);

ws.on('open', () => {
    console.log('WebSocket connection opened.');
    console.log(`Subscribing to orderbook for ${config.SYMBOL}...`);
    ws.send(JSON.stringify({
        op: 'subscribe',
        args: [`orderbook.1.${config.SYMBOL}`] // orderbook.1 is enough for top-of-book
    }));
});

ws.on('message', async (data) => {
    try {
        const msg = JSON.parse(data);

        // Handle subscription confirmation
        if (msg.op === 'subscribe' && msg.success) {
            console.log(`Successfully subscribed to ${msg.args.join(', ')}`);
            return;
        }

        // Handle orderbook updates
        if (msg.topic && msg.topic.startsWith(`orderbook.1.${config.SYMBOL}`)) {
            const orderbook = msg.data;
            bestBid = parseFloat(orderbook.b[0][0]);
            bestAsk = parseFloat(orderbook.a[0][0]);
        }
    } catch (error) {
        console.error('Error processing WebSocket message:', error);
    }
});

ws.on('error', (error) => {
    console.error('WebSocket error:', error);
});

ws.on('close', () => {
    console.log('WebSocket connection closed. You may need to restart the bot.');
    // A production bot would have more robust reconnection logic here.
});


// --- Order Management Logic ---
async function updateMarketMakerOrders() {
    if (isUpdating || bestBid === 0 || bestAsk === 0) {
        return; // Don't update if already in progress or no valid price
    }
    isUpdating = true;
    console.log(`
Updating orders at ${new Date().toISOString()}`);
    console.log(`Best Bid: ${bestBid}, Best Ask: ${bestAsk}`);

    try {
        // 1. Cancel all existing orders for the symbol
        console.log(`Canceling all existing ${config.SYMBOL} orders...`);
        const cancelResult = await cancelAllOrders(config.SYMBOL, config.CATEGORY);
        if (cancelResult && cancelResult.retCode === 0) {
            console.log('Successfully canceled orders.');
        } else {
            console.error('Failed to cancel orders.');
        }

        // 2. Place new bid and ask orders
        const midPrice = (bestBid + bestAsk) / 2;
        const bidPrice = (midPrice - config.SPREAD / 2).toFixed(2);
        const askPrice = (midPrice + config.SPREAD / 2).toFixed(2);

        console.log(`Placing new orders: Buy at ${bidPrice}, Sell at ${askPrice}`);

        const buyOrder = {
            category: config.CATEGORY,
            symbol: config.SYMBOL,
            side: 'Buy',
            orderType: 'Limit',
            qty: config.ORDER_QTY,
            price: bidPrice,
            timeInForce: 'PostOnly', // Ensure it's a maker order
        };

        const sellOrder = {
            category: config.CATEGORY,
            symbol: config.SYMBOL,
            side: 'Sell',
            orderType: 'Limit',
            qty: config.ORDER_QTY,
            price: askPrice,
            timeInForce: 'PostOnly', // Ensure it's a maker order
        };

        const [buyResult, sellResult] = await Promise.all([
            placeOrder(buyOrder),
            placeOrder(sellOrder)
        ]);

        if (buyResult && buyResult.retCode === 0) {
            console.log(`Placed Buy order: ${buyResult.result.orderId}`);
        } else {
             console.error('Failed to place Buy order.');
        }
        if (sellResult && sellResult.retCode === 0) {
            console.log(`Placed Sell order: ${sellResult.result.orderId}`);
        } else {
            console.error('Failed to place Sell order.');
        }

    } catch (error) {
        console.error('An error occurred during the order update cycle:', error);
    } finally {
        isUpdating = false;
    }
}

// --- Main Loop ---
// Use a timer to update orders periodically
setInterval(updateMarketMakerOrders, config.REFRESH_MS);
