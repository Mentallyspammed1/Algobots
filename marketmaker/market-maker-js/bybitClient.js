const axios = require('axios');
const crypto = require('crypto');
require('dotenv').config();

const API_KEY = process.env.BYBIT_API_KEY;
const API_SECRET = process.env.BYBIT_API_SECRET;
const IS_TESTNET = process.env.BYBIT_TESTNET === 'true';
const BASE_URL = IS_TESTNET ? 'https://api-testnet.bybit.com' : 'https://api.bybit.com';
const RECV_WINDOW = 5000;

async function makePostRequest(endpoint, params) {
    const timestamp = Date.now().toString();
    const paramString = JSON.stringify(params);
    const signaturePayload = timestamp + API_KEY + RECV_WINDOW + paramString;
    const signature = crypto.createHmac('sha256', API_SECRET).update(signaturePayload).digest('hex');

    const headers = {
        'X-BAPI-API-KEY': API_KEY,
        'X-BAPI-TIMESTAMP': timestamp,
        'X-BAPI-RECV-WINDOW': RECV_WINDOW,
        'X-BAPI-SIGN': signature,
        'Content-Type': 'application/json',
    };

    const url = `${BASE_URL}${endpoint}`;

    try {
        const response = await axios.post(url, params, { headers });
        if (response.data.retCode !== 0) {
            console.error(`Bybit API Error: ${response.data.retMsg} (Code: ${response.data.retCode})`);
        }
        return response.data;
    } catch (error) {
        console.error('Error making POST request to Bybit API:', error.response ? error.response.data : error.message);
        return null;
    }
}

const placeOrder = (order) => makePostRequest('/v5/order/create', order);
const cancelAllOrders = (symbol, category = 'linear') => makePostRequest('/v5/order/cancel-all', { symbol, category });

module.exports = {
    placeOrder,
    cancelAllOrders,
    IS_TESTNET,
};
