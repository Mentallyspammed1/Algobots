
Here's a comprehensive list of JavaScript libraries commonly used for Bybit API integration and market making:

### Core API Interaction Libraries
1. **axios**  
   *Promise-based HTTP client for REST API calls*  
   `npm install axios`

2. **ws**  
   *WebSocket client for real-time market data*  
   `npm install ws`

3. **node-fetch**  
   *Lightweight HTTP client alternative to axios*  
   `npm install node-fetch`

4. **form-data**  
   *For handling multipart/form-data payloads*  
   `npm install form-data`

---

### Cryptography & Security
5. **crypto** (built-in)  
   *Node.js built-in for HMAC-SHA256 signatures*  
   *No installation required*

6. **uuid**  
   *For generating unique request IDs*  
   `npm install uuid`

---

### Utilities
7. **date-fns**  
   *For timestamp formatting and timezone handling*  
   `npm install date-fns`

8. **dotenv**  
   *Environment variable management*  
   `npm install dotenv`

9. **ws-reconnect**  
   *WebSocket reconnection helper*  
   `npm install ws-reconnect`

---

### Bybit-Specific Tools (Community)
10. **bybit-api**  
    *Unofficial TypeScript wrapper*  
    `npm install bybit-api`  
    *GitHub: [bybit-api](https://github.com/bybit-exchange/bybit-api)*

11. **bybit-webSocket**  
    *Community WebSocket helper*  
    *Search npm for latest packages*

---

### Advanced Use Cases
12. **ccxt**  
    *Unified crypto exchange API wrapper*  
    `npm install ccxt`  
    *Supports Bybit REST API*

13. **p-queue**  
    *Rate limiting and concurrency control*  
    `npm install p-queue`

14. **ws-json-stream**  
    *JSON message parsing for WebSocket*  
    `npm install ws-json-stream`

---

### Development Tools
15. **typescript**  
    *For type-safe development*  
    `npm install typescript`

16. **jest**  
    *Testing framework*  
    `npm install jest`

17. **nodemon**  
    *Development server auto-reload*  
    `npm install nodemon --save-dev`

---

### Key Considerations:
1. **No Official SDK**: Bybit doesn't maintain an official JavaScript SDK
2. **API Version**: Most libraries work with Bybit API v5 (current version)
3. **WebSocket vs REST**: Use `ws` for real-time data, `axios`/`node-fetch` for REST
4. **TypeScript Support**: Many packages include TypeScript definitions

For a market maker bot, you'll primarily need:
- `axios`/`node-fetch` for order management
- `ws` for orderbook updates
- `crypto` for authentication
- `date-fns` for timestamp handling

Would you like me to provide a more detailed example using any specific combination of these libraries?Below is a comprehensive list of Bybit API endpoints with JavaScript code snippets. These examples use `axios` for REST and `ws` for WebSocket connections. Always test in Bybit's [testnet](https://testnet.bybit.com/) first.

---

### **Authentication Setup**
All authenticated endpoints require HMAC-SHA256 signatures:
```javascript
const crypto = require('crypto');

function generateSignature(params, secret) {
  const sortedParams = Object.keys(params)
    .sort()
    .map(k => `${k}=${params[k]}`)
    .join('&');
  return crypto
    .createHmac('sha256', secret)
    .update(sortedParams)
    .digest('hex');
}
```

---

### **1. Public Endpoints (No Authentication)**
#### **Server Time**
```javascript
const axios = require('axios');

async function getServerTime() {
  const response = await axios.get('https://api.bybit.com/v5/public/time');
  console.log(response.data);
}
```

#### **Orderbook (L2)**
```javascript
async function getOrderbook(symbol = 'BTCUSDT') {
  const response = await axios.get(
    `https://api.bybit.com/v5/public/linear/orderbook?symbol=${symbol}&limit=200`
  );
  console.log(response.data);
}
```

---

### **2. Market Data Endpoints**
#### **Latest Trades**
```javascript
async function getTrades(symbol = 'BTCUSDT') {
  const response = await axios.get(
    `https://api.bybit.com/v5/public/linear/recent-trade?symbol=${symbol}&limit=10`
  );
  console.log(response.data);
}
```

#### **Kline/Candlestick Data**
```javascript
async function getKlines(symbol = 'BTCUSDT', interval = '1h', limit = 100) {
  const response = await axios.get(
    `https://api.bybit.com/v5/public/linear/kline?symbol=${symbol}&interval=${interval}&limit=${limit}`
  );
  console.log(response.data);
}
```

---

### **3. Trading Endpoints (Authenticated)**
#### **Place Order**
```javascript
async function placeOrder(symbol, side, price, qty) {
  const timestamp = Date.now();
  const params = {
    api_key: 'YOUR_API_KEY',
    category: 'linear',
    symbol: symbol,
    side: side, // "Buy" or "Sell"
    orderType: 'Limit',
    price: price,
    qty: qty,
    timeInForce: 'GoodTillCancel',
    timestamp: timestamp
  };

  const signature = generateSignature(params, 'YOUR_API_SECRET');
  
  const response = await axios.post(
    'https://api.bybit.com/v5/order/create',
    null,
    { params: { ...params, sign: signature } }
  );
  console.log(response.data);
}
```

#### **Cancel All Orders**
```javascript
async function cancelAllOrders(symbol) {
  const timestamp = Date.now();
  const params = {
    api_key: 'YOUR_API_KEY',
    category: 'linear',
    symbol: symbol,
    timestamp: timestamp
  };

  const signature = generateSignature(params, 'YOUR_API_SECRET');
  
  const response = await axios.post(
    'https://api.bybit.com/v5/order/cancel-all',
    null,
    { params: { ...params, sign: signature } }
  );
  console.log(response.data);
}
```

#### **Get Open Orders**
```javascript
async function getOpenOrders(symbol) {
  const timestamp = Date.now();
  const params = {
    api_key: 'YOUR_API_KEY',
    category: 'linear',
    symbol: symbol,
    timestamp: timestamp
  };

  const signature = generateSignature(params, 'YOUR_API_SECRET');
  
  const response = await axios.get(
    'https://api.bybit.com/v5/order/list',
    { params: { ...params, sign: signature } }
  );
  console.log(response.data);
}
```

---

### **4. WebSocket Integration (Real-Time Data)**
#### **Orderbook Updates**
```javascript
const WebSocket = require('ws');

function connectOrderbookStream(symbol = 'BTCUSDT') {
  const ws = new WebSocket('wss://stream.bybit.com/v5/public/linear');

  ws.on('open', () => {
    ws.send(JSON.stringify({
      op: 'subscribe',
      args: [`orderbook.200.${symbol}`]
    }));
  });

  ws.on('message', (data) => {
    const message = JSON.parse(data);
    if (message.topic?.includes(symbol)) {
      console.log('Orderbook Update:', message.data);
    }
  });
}
```

#### **Trade Stream**
```javascript
function connectTradeStream(symbol = 'BTCUSDT') {
  const ws = new WebSocket('wss://stream.bybit.com/v5/public/linear');

  ws.on('open', () => {
    ws.send(JSON.stringify({
      op: 'subscribe',
      args: [`publicTrade.${symbol}`]
    }));
  });

  ws.on('message', (data) => {
    const message = JSON.parse(data);
    if (message.topic?.startsWith('publicTrade')) {
      console.log('New Trade:', message.data);
    }
  });
}
```

---

### **5. Positions & Risk Management**
#### **Get Position Data**
```javascript
async function getPositions(symbol) {
  const timestamp = Date.now();
  const params = {
    api_key: 'YOUR_API_KEY',
    category: 'linear',
    symbol: symbol,
    timestamp: timestamp
  };

  const signature = generateSignature(params, 'YOUR_API_SECRET');
  
  const response = await axios.get(
    'https://api.bybit.com/v5/position/list',
    { params: { ...params, sign: signature } }
  );
  console.log(response.data);
}
```

#### **Set Leverage**
```javascript
async function setLeverage(symbol, leverage) {
  const timestamp = Date.now();
  const params = {
    api_key: 'YOUR_API_KEY',
    category: 'linear',
    symbol: symbol,
    buyLeverage: leverage,
    sellLeverage: leverage,
    timestamp: timestamp
  };

  const signature = generateSignature(params, 'YOUR_API_SECRET');
  
  const response = await axios.post(
    'https://api.bybit.com/v5/position/set-leverage',
    null,
    { params: { ...params, sign: signature } }
  );
  console.log(response.data);
}
```

---

### **Full Market Maker Bot (Combined Example)**
```javascript
// Requires: axios, ws, crypto
const WebSocket = require('ws');
const axios = require('axios');
const crypto = require('crypto');

const config = {
  API_KEY: 'YOUR_API_KEY',
  API_SECRET: 'YOUR_API_SECRET',
  SYMBOL: 'BTCUSDT',
  SPREAD: 0.5, // USDT
  ORDER_QTY: '0.001'
};

let bestBid = 0;
let bestAsk = 0;

// WebSocket Orderbook Listener
const ws = new WebSocket('wss://stream.bybit.com/v5/public/linear');

ws.on('open', () => {
  ws.send(JSON.stringify({
    op: 'subscribe',
    args: [`orderbook.200.${config.SYMBOL}`]
  }));
});

ws.on('message', async (data) => {
  try {
    const msg = JSON.parse(data);
    if (msg.topic?.startsWith(`orderbook.200.${config.SYMBOL}`)) {
      bestBid = parseFloat(msg.data.bids[0][0]);
      bestAsk = parseFloat(msg.data.asks[0][0]);
      await updateMMOrders();
    }
  } catch (error) {
    console.error('WebSocket error:', error);
  }
});

// Order Management
async function updateMMOrders() {
  await cancelAllOrders();
  const bidPrice = (bestBid - config.SPREAD).toFixed(2);
  const askPrice = (bestAsk + config.SPREAD).toFixed(2);
  await Promise.all([
    placeOrder('Buy', bidPrice),
    placeOrder('Sell', askPrice)
  ]);
}

// Reuse the placeOrder() and cancelAllOrders() functions from earlier
```

---

### Key Notes:
1. **Testnet URL**: Replace `api.bybit.com` with `api-testnet.bybit.com` for testing
2. **Rate Limits**: Bybit enforces strict rate limits (~50 requests/second)
3. **Error Handling**: Add retries for failed requests
4. **Risk Management**: Add position size checks and stop-loss logic
5. **WebSocket Reconnect**: Implement reconnection logic for stability

Would you like me to expand on any specific endpoint or functionality?
