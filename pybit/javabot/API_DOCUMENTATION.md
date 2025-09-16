# Bybit API Client Documentation

This document provides API documentation for the `BybitAPIClient` class, which is used to interact with the Bybit V5 API.

## Initialization

First, you need to import the `bybitClient` instance:

```javascript
import { bybitClient } from './bybit_api_client.js';
```

The client is automatically initialized with your API keys and settings from `config.js` and `.env`.

---

## Methods

### `getBalance(coin)`

**Description:** Fetches the wallet balance for a specified coin. In dry-run mode, returns a simulated balance.

**Parameters:**

| Name   | Type     | Description                               | Default |
| :----- | :------- | :---------------------------------------- | :------ |
| `coin` | `string` | The cryptocurrency symbol (e.g., "USDT"). | "USDT"  |

**Returns:**

*   `Promise<number>` - The wallet balance as a float, or 0 if not found/error.

**Example:**

```javascript
const usdtBalance = await bybitClient.getBalance('USDT');
console.log(`My USDT Balance: ${usdtBalance}`);

const btcBalance = await bybitClient.getBalance('BTC');
console.log(`My BTC Balance: ${btcBalance}`);
```

---

### `getPositions(settleCoin)`

**Description:** Retrieves a list of open positions. In dry-run mode, returns simulated open positions.

**Parameters:**

| Name         | Type     | Description                               | Default |
| :----------- | :------- | :---------------------------------------- | :------ |
| `settleCoin` | `string` | The settlement coin for the positions.    | "USDT"  |

**Returns:**

*   `Promise<Array<Object>>` - An array of open position objects.

**Example:**

```javascript
const openPositions = await bybitClient.getPositions('USDT');
if (openPositions.length > 0) {
  console.log('Open Positions:', openPositions);
} else {
  console.log('No open positions.');
}
```

---

### `getTickers()`

**Description:** Fetches a list of tradable symbols (tickers) that include 'USDT' and exclude 'USDC'.

**Returns:**

*   `Promise<Array<string>|null>` - An array of symbol strings (e.g., `["BTCUSDT", "ETHUSDT"]`), or `null` on error.

**Example:**

```javascript
const tickers = await bybitClient.getTickers();
if (tickers) {
  console.log('Available USDT tickers:', tickers);
}
```

---

### `klines(symbol, timeframe, limit)`

**Description:** Retrieves historical candlestick data for a given symbol and timeframe.

**Parameters:**

| Name        | Type     | Description                               | Default |
| :---------- | :------- | :---------------------------------------- | :------ |
| `symbol`    | `string` | The trading pair symbol (e.g., "BTCUSDT"). |         |
| `timeframe` | `string` | The kline interval (e.g., "1", "5", "D"). |         |
| `limit`     | `number` | The maximum number of klines to retrieve. | 500     |

**Returns:**

*   `Promise<Array<Object>>` - An array of kline objects, each with `time`, `open`, `high`, `low`, `close`, `volume`, and `turnover`.

**Example:**

```javascript
const btcKlines = await bybitClient.klines('BTCUSDT', '60', 100);
console.log('Last 100 hourly BTC/USDT klines:', btcKlines);
```

---

### `getCurrentPrice(symbol)`

**Description:** Fetches the last traded price for a given symbol.

**Parameters:**

| Name     | Type     | Description                               |
| :------- | :------- | :---------------------------------------- |
| `symbol` | `string` | The trading pair symbol (e.g., "BTCUSDT"). |

**Returns:**

*   `Promise<number|null>` - The current price as a float, or `null` on error.

**Example:**

```javascript
const ethPrice = await bybitClient.getCurrentPrice('ETHUSDT');
if (ethPrice) {
  console.log('Current ETH/USDT price:', ethPrice);
}
```

---

### `getOrderbookLevels(symbol, limit)`

**Description:** Retrieves the best bid and best ask prices from the order book.

**Parameters:**

| Name     | Type     | Description                               | Default |
| :------- | :------- | :---------------------------------------- | :------ |
| `symbol` | `string` | The trading pair symbol (e.g., "BTCUSDT"). |         |
| `limit`  | `number` | The number of order book levels to retrieve. | 50      |

**Returns:**

*   `Promise<Array<number|null>>` - An array containing `[bestBid, bestAsk]`, or `[null, null]` on error.

**Example:**

```javascript
const [bestBid, bestAsk] = await bybitClient.getOrderbookLevels('BTCUSDT');
console.log(`BTC/USDT Best Bid: ${bestBid}, Best Ask: ${bestAsk}`);
```

---

### `getPrecisions(symbol)`

**Description:** Fetches price and quantity precision (step sizes) and minimum order quantity for a symbol.

**Parameters:**

| Name     | Type     | Description                               |
| :------- | :------- | :---------------------------------------- |
| `symbol` | `string` | The trading pair symbol (e.g., "BTCUSDT"). |

**Returns:**

*   `Promise<Array<number>>` - An array containing `[pricePrecision, qtyPrecision, minOrderQty]`.

**Example:**

```javascript
const [pricePrec, qtyPrec, minQty] = await bybitClient.getPrecisions('ETHUSDT');
console.log(`ETH/USDT - Price Precision: ${pricePrec}, Quantity Precision: ${qtyPrec}, Min Order Qty: ${minQty}`);
```

---

### `setMarginModeAndLeverage(symbol, mode, leverage)`

**Description:** Sets the margin mode (isolated/cross) and leverage for a given symbol.

**Parameters:**

| Name       | Type     | Description                               |
| :--------- | :------- | :---------------------------------------- |
| `symbol`   | `string` | The trading pair symbol (e.g., "BTCUSDT"). |
| `mode`     | `number` | Margin mode: `0` for Cross, `1` for Isolated. |
| `leverage` | `number` | The desired leverage value (e.g., 10).   |

**Returns:**

*   `Promise<void>`

**Example:**

```javascript
// Set isolated margin with 25x leverage for SOL/USDT
await bybitClient.setMarginModeAndLeverage('SOLUSDT', 1, 25);
```

---

### `placeMarketOrder(symbol, side, qty, tpPrice, slPrice, reduceOnly)`

**Description:** Places a market order.

**Parameters:**

| Name         | Type      | Description                               | Default |
| :----------- | :-------- | :---------------------------------------- | :------ |
| `symbol`     | `string`  | The trading pair symbol (e.g., "BTCUSDT"). |         |
| `side`       | `string`  | Order side: "Buy" or "Sell".              |         |
| `qty`        | `number`  | The quantity of the asset to trade.       |         |
| `tpPrice`    | `number`  | Take Profit price.                        | `null`  |
| `slPrice`    | `number`  | Stop Loss price.                          | `null`  |
| `reduceOnly` | `boolean` | Whether the order is to reduce a position. | `false` |

**Returns:**

*   `Promise<string|null>` - The order ID if successful, or `null` on failure.

**Example:**

```javascript
const orderId = await bybitClient.placeMarketOrder('BTCUSDT', 'Buy', 0.01, 46000, 44000);
if (orderId) {
  console.log('Market order placed successfully. Order ID:', orderId);
}
```

---

### `placeLimitOrder(symbol, side, price, qty, tpPrice, slPrice, timeInForce, reduceOnly)`

**Description:** Places a limit order.

**Parameters:**

| Name          | Type      | Description                               | Default |
| :------------ | :-------- | :---------------------------------------- | :------ |
| `symbol`      | `string`  | The trading pair symbol (e.g., "BTCUSDT"). |         |
| `side`        | `string`  | Order side: "Buy" or "Sell".              |         |
| `price`       | `number`  | The price for the limit order.            |         |
| `qty`         | `number`  | The quantity of the asset to trade.       |         |
| `tpPrice`     | `number`  | Take Profit price.                        | `null`  |
| `slPrice`     | `number`  | Stop Loss price.                          | `null`  |
| `timeInForce` | `string`  | Time in Force policy (e.g., "GTC", "IOC"). | "GTC"   |
| `reduceOnly`  | `boolean` | Whether the order is to reduce a position. | `false` |

**Returns:**

*   `Promise<string|null>` - The order ID if successful, or `null` on failure.

**Example:**

```javascript
const orderId = await bybitClient.placeLimitOrder('ETHUSDT', 'Sell', 3000, 0.5, null, 3100, 'GTC', true);
if (orderId) {
  console.log('Limit order placed successfully. Order ID:', orderId);
}
```

---

### `placeConditionalOrder(symbol, side, qty, triggerPrice, orderType, price, tpPrice, slPrice, reduceOnly)`

**Description:** Places a conditional order (e.g., Stop Market, Stop Limit).

**Parameters:**

| Name           | Type      | Description                               | Default  |
| :------------- | :-------- | :---------------------------------------- | :------- |
| `symbol`       | `string`  | The trading pair symbol (e.g., "BTCUSDT"). |          |
| `side`         | `string`  | Order side: "Buy" or "Sell".              |          |
| `qty`          | `number`  | The quantity of the asset to trade.       |          |
| `triggerPrice` | `number`  | The price that triggers the order.        |          |
| `orderType`    | `string`  | Type of order once triggered ("Market" or "Limit"). | "Market" |
| `price`        | `number`  | The limit price if `orderType` is "Limit". | `null`   |
| `tpPrice`      | `number`  | Take Profit price.                        | `null`   |
| `slPrice`      | `number`  | Stop Loss price.                          | `null`   |
| `reduceOnly`   | `boolean` | Whether the order is to reduce a position. | `false`  |

**Returns:**

*   `Promise<string|null>` - The order ID if successful, or `null` on failure.

**Example:**

```javascript
// Place a Stop Market order to buy 0.1 BTC if the price reaches 45000
const orderId = await bybitClient.placeConditionalOrder('BTCUSDT', 'Buy', 0.1, 45000);
if (orderId) {
  console.log('Conditional order placed. Order ID:', orderId);
}
```

---

### `cancelAllOpenOrders(symbol)`

**Description:** Cancels all active open orders for a given symbol.

**Parameters:**

| Name     | Type     | Description                               |
| :------- | :------- | :---------------------------------------- |
| `symbol` | `string` | The trading pair symbol (e.g., "BTCUSDT"). |

**Returns:**

*   `Promise<Object>` - The API response object.

**Example:**

```javascript
await bybitClient.cancelAllOpenOrders('BTCUSDT');
```

---

### `modifyPositionTpsl(symbol, tpPrice, slPrice)`

**Description:** Modifies the Take Profit (TP) and Stop Loss (SL) levels for an existing position.

**Parameters:**

| Name      | Type     | Description                               |
| :-------- | :------- | :---------------------------------------- |
| `symbol`  | `string` | The trading pair symbol (e.g., "BTCUSDT"). |
| `tpPrice` | `number` | The new Take Profit price.                |
| `slPrice` | `number` | The new Stop Loss price.                  |

**Returns:**

*   `Promise<Object>` - The API response object.

**Example:**

```javascript
// Update the TP/SL for an existing BTCUSDT position
await bybitClient.modifyPositionTpsl('BTCUSDT', 48000, 44500);
```

---

### `getOpenOrders(symbol)`

**Description:** Retrieves a list of active open orders for a given symbol, or all symbols if none specified.

**Parameters:**

| Name     | Type     | Description                               | Default |
| :------- | :------- | :---------------------------------------- | :------ |
| `symbol` | `string` | The trading pair symbol (e.g., "BTCUSDT"). | `null`  |

**Returns:**

*   `Promise<Array<Object>>` - An array of open order objects.

**Example:**

```javascript
const openOrders = await bybitClient.getOpenOrders('ETHUSDT');
console.log('Open ETH/USDT orders:', openOrders);
```

---

### `closePosition(symbol)`

**Description:** Closes an existing open position for a given symbol using a market order.

**Parameters:**

| Name     | Type     | Description                               |
| :------- | :------- | :---------------------------------------- |
| `symbol` | `string` | The trading pair symbol (e.g., "BTCUSDT"). |

**Returns:**

*   `Promise<string|null>` - The order ID of the closing order if successful, or `null` on failure.

**Example:**

```javascript
const closingOrderId = await bybitClient.closePosition('BTCUSDT');
if (closingOrderId) {
  console.log('Position closed. Closing order ID:', closingOrderId);
}
```
