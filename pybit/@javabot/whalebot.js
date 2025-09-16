require('dotenv').config();
const axios = require('axios');
const crypto = require('crypto');
const { exec } = require('child_process');

const BASE_URL = 'https://api.bybit.com';

const API_KEY = process.env.API_KEY;
const API_SECRET = process.env.API_SECRET;

const TRADE_AMOUNT = 0.001;
const TP_PERCENT = 0.02;
const SL_PERCENT = 0.01;

const ALERT_PHONE_NUMBER = '+1234567890';

let activeOrders = {
  tpOrderId: null,
  slOrderId: null,
  entryPrice: null,
  positionSide: null,
};

function sendSMS(message) {
  const command = `termux-sms-send -n ${ALERT_PHONE_NUMBER} "${message}"`;
  exec(command, (error, stdout, stderr) => {
    if (error) {
      console.error(`Error sending SMS: ${error.message}`);
      return;
    }
    console.log(`SMS sent: ${message}`);
  });
}

function authHeaders(endpoint, method = 'GET', bodyStr = '') {
  const timestamp = new Date().toISOString();
  const preHash = timestamp + method.toUpperCase() + endpoint + bodyStr;
  const signature = crypto.createHmac('sha256', API_SECRET).update(preHash).digest('hex');
  return {
    'X-BAPI-API-KEY': API_KEY,
    'X-BAPI-TIMESTAMP': timestamp,
    'X-BAPI-SIGNATURE': signature,
    'Content-Type': 'application/json',
  };
}

async function getCurrentPosition() {
  const endpoint = '/v2/private/position/list';
  const url = `${BASE_URL}${endpoint}?symbol=BTCUSD`;
  const headers = authHeaders(endpoint);
  try {
    const resp = await axios.get(url, { headers });
    const positions = resp.data.result;
    const position = positions.find(p => p.symbol === 'BTCUSD');
    if (position && parseFloat(position.size) > 0) {
      return position.side === 'Buy' ? 'long' : 'short';
    } else {
      return 'flat';
    }
  } catch (err) {
    console.error('Error fetching position:', err.message);
    return 'flat';
  }
}

async function getLatestClose() {
  const resp = await axios.get(`${BASE_URL}/public/ohlcv?symbol=BTCUSD&interval=1&limit=1`);
  if (resp.data.result && resp.data.result.length > 0) {
    return resp.data.result[0].close;
  }
  return null;
}

async function placeMarketOrder(side, qty) {
  const endpoint = '/v2/private/order/create';
  const body = {
    symbol: 'BTCUSD',
    side,
    order_type: 'Market',
    qty,
    time_in_force: 'GoodTillCancel',
  };
  const bodyStr = JSON.stringify(body);
  const headers = authHeaders(endpoint, 'POST', bodyStr);
  const resp = await axios.post(`${BASE_URL}${endpoint}`, body, { headers });
  return resp.data.result;
}

async function placeLimitOrder(side, price, qty) {
  const endpoint = '/v2/private/order/create';
  const body = {
    symbol: 'BTCUSD',
    side,
    order_type: 'Limit',
    qty,
    price,
    time_in_force: 'GoodTillCancel',
  };
  const bodyStr = JSON.stringify(body);
  const headers = authHeaders(endpoint, 'POST', bodyStr);
  const resp = await axios.post(`${BASE_URL}${endpoint}`, body, { headers });
  return resp.data.result;
}

async function placeStopOrder(side, stop_px, qty) {
  const endpoint = '/v2/private/order/create';
  const body = {
    symbol: 'BTCUSD',
    side,
    order_type: 'Stop',
    qty,
    stop_px,
    base_price: stop_px,
    stop_order_type: 'Stop',
    time_in_force: 'GoodTillCancel',
  };
  const bodyStr = JSON.stringify(body);
  const headers = authHeaders(endpoint, 'POST', bodyStr);
  const resp = await axios.post(`${BASE_URL}${endpoint}`, body, { headers });
  return resp.data.result;
}

async function getOrderStatus(orderId) {
  const endpoint = '/v2/private/order/list';
  const url = `${BASE_URL}${endpoint}?order_id=${orderId}`;
  const headers = authHeaders(endpoint);
  const resp = await axios.get(url, { headers });
  if (resp.data.result && resp.data.result.length > 0) {
    return resp.data.result[0];
  }
  return null;
}

async function cancelOrder(orderId) {
  const endpoint = '/v2/private/order/cancel';
  const body = {
    order_id: orderId
  };
  const bodyStr = JSON.stringify(body);
  const headers = authHeaders(endpoint, 'POST', bodyStr);
  const resp = await axios.post(`${BASE_URL}${endpoint}`, body, { headers });
  return resp.data;
}

async function enterPosition(side) {
  console.log(`Entering ${side} position...`);
  const currentPrice = await getLatestClose();
  if (!currentPrice) {
    console.log('Failed to fetch current price.');
    return;
  }
  console.log('Current Price:', currentPrice);

  const entryOrder = await placeMarketOrder(side, TRADE_AMOUNT);
  console.log(`${side} market order placed, order_id: ${entryOrder.order_id}`);
  sendSMS(`Market ${side} order placed for ${TRADE_AMOUNT} BTC. Price: ${currentPrice}`);

  activeOrders.entryPrice = parseFloat(currentPrice);
  activeOrders.positionSide = side;

  const tpPrice = side === 'long' ?
    activeOrders.entryPrice * (1 + TP_PERCENT) :
    activeOrders.entryPrice * (1 - TP_PERCENT);
  const slPrice = side === 'long' ?
    activeOrders.entryPrice * (1 - SL_PERCENT) :
    activeOrders.entryPrice * (1 + SL_PERCENT);

  const tpSide = side === 'long' ? 'Sell' : 'Buy';
  const tpOrder = await placeLimitOrder(tpSide, tpPrice, TRADE_AMOUNT);
  console.log(`TP order placed at ${tpPrice}, order_id: ${tpOrder.order_id}`);
  sendSMS(`TP order placed at ${tpPrice}`);

  const slSide = side === 'long' ? 'Sell' : 'Buy';
  const slOrder = await placeStopOrder(slSide, slPrice, TRADE_AMOUNT);
  console.log(`SL order placed at ${slPrice}, order_id: ${slOrder.order_id}`);
  sendSMS(`SL order placed at ${slPrice}`);

  activeOrders.tpOrderId = tpOrder.order_id;
  activeOrders.slOrderId = slOrder.order_id;
}

async function manageTP_SLOrders() {
  if (!activeOrders.tpOrderId || !activeOrders.slOrderId) return;

  const tpStatus = await getOrderStatus(activeOrders.tpOrderId);
  const slStatus = await getOrderStatus(activeOrders.slOrderId);

  if (tpStatus && tpStatus.order_status === 'Filled') {
    console.log('TP order filled, closing position...');
    sendSMS(`TP for ${activeOrders.positionSide} filled!`);
    activeOrders.tpOrderId = null;
    activeOrders.slOrderId = null;
    activeOrders.entryPrice = null;
    activeOrders.positionSide = null;
    return;
  } else if (tpStatus && tpStatus.order_status === 'Canceled') {
    console.log('TP order canceled, replacing...');
    sendSMS(`TP order canceled and replaced.`);
    const newPrice = activeOrders.positionSide === 'long' ?
      activeOrders.entryPrice * (1 + TP_PERCENT) :
      activeOrders.entryPrice * (1 - TP_PERCENT);
    const newOrder = await placeLimitOrder(
      activeOrders.positionSide === 'long' ? 'Sell' : 'Buy',
      newPrice,
      TRADE_AMOUNT
    );
    activeOrders.tpOrderId = newOrder.order_id;
    console.log('Replaced TP at', newPrice);
  }

  if (slStatus && slStatus.order_status === 'Filled') {
    console.log('SL order filled, position closed.');
    sendSMS(`SL for ${activeOrders.positionSide} filled!`);
    activeOrders.tpOrderId = null;
    activeOrders.slOrderId = null;
    activeOrders.entryPrice = null;
    activeOrders.positionSide = null;
    return;
  } else if (slStatus && slStatus.order_status === 'Canceled') {
    console.log('SL order canceled, replacing...');
    sendSMS(`SL order canceled and replaced.`);
    const newPrice = activeOrders.positionSide === 'long' ?
      activeOrders.entryPrice * (1 - SL_PERCENT) :
      activeOrders.entryPrice * (1 + SL_PERCENT);
    const newOrder = await placeStopOrder(
      activeOrders.positionSide === 'long' ? 'Sell' : 'Buy',
      newPrice,
      TRADE_AMOUNT
    );
    activeOrders.slOrderId = newOrder.order_id;
    console.log('Replaced SL at', newPrice);
  }
}

async function main() {
  while (true) {
    try {
      const position = await getCurrentPosition();
      console.log(`Current position: ${position}`);

      if (position === 'flat') {
        await enterPosition('long');
      } else {
        await manageTP_SLOrders();
      }
    } catch (err) {
      console.error('Error in main loop:', err.message);
      sendSMS(`Bot Error: ${err.message}`);
    }
    await new Promise(r => setTimeout(r, 60 * 1000));
  }
}

main();
