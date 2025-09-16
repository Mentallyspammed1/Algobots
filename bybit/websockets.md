### 1. Official Documentation (The Best Source)

The absolute best place to start is Bybit's official
API documentation. They keep it updated with the
latest versions and features.

*   **Bybit API Documentation Portal:** [https://
bybit-exchange.github.io/docs/](https://bybit-
exchange.github.io/docs/)
*   **Direct Link to WebSocket Connect (v5,
current):** [https://bybit-exchange.github.io/docs/
v5/ws/connect](https://bybit-exchange.github.io/docs/
v5/ws/connect)

**Key sections to look for in the documentation:**

*   **Connection URLs:** Different URLs for Spot,
Derivatives (USDT Perpetuals, Inverse Perpetuals,
USDC Contracts), and Options, as well as for
production and testnet environments.
*   **Public vs. Private WebSockets:**
    *   **Public:** For market data (order book,
trades, tickers, klines). No authentication required.
    *   **Private:** For user-specific data (order
updates, position updates, account balance). Requires
authentication using your API Key and Secret.
*   **Subscription/Unsubscription:** How to send
messages to subscribe to specific topics (e.g.,
`orderbook`, `trade`, `kline`, `order`, `position`).
*   **Authentication:** Detailed steps on how to
authenticate for private channels (usually involves
sending an `auth` message with a signed payload).
*   **Message Formats:** How the data is structured
when received from the WebSocket.
*   **Heartbeat (Ping/Pong):** How to keep the
connection alive.
*   **Rate Limits & Connection Limits:** Important
for stable applications.

---

### 2. Key Concepts & URLs (v5 - Current Version)

Bybit's v5 API is the current standard.

**General Structure:**

*   **Public WebSockets:** `wss://stream.bybit.com/
v5/public/{product_type}`
*   **Private WebSockets:** `wss://stream.bybit.com/
v5/private` (This single endpoint handles private
data for all product types)

**Example Connection URLs (Production):**

*   **USDT Perpetuals & USDC Contract (Public):**
`wss://stream.bybit.com/v5/public/linear`
*   **Inverse Perpetuals & Futures (Public):**
`wss://stream.bybit.com/v5/public/inverse`
*   **Spot (Public):** `wss://stream.bybit.com/v5/
public/spot`
*   **Options (Public):** `wss://stream.bybit.com/v5/
public/option`
*   **All Private Channels:** `wss://
stream.bybit.com/v5/private`

**Testnet URLs:** Replace `stream.bybit.com` with
`stream-testnet.bybit.com`.

---

### 3. Common Operations

*   **Connecting:** Establish a WebSocket connection
to the appropriate URL.
*   **Subscribing:** Send a JSON message like:
    ```json
    {
        "op": "subscribe",
        "args": ["topic.symbol"] // e.g.,
"orderbook.50.BTCUSDT", "kline.1.BTCUSDT", "order"
    }
    ```
*   **Authenticating (for Private):** After
connecting, send an `auth` message with your API key,
a timestamp, and a signature generated using your API
secret.
    ```json
    {
        "op": "auth",
        "args": ["YOUR_API_KEY", TIMESTAMP_IN_MS,
"SIGNATURE"]
    }
    ```
    The signature is typically HMAC-SHA256 of `GET/
realtimeAPIKEYTIMESTAMP` using your API Secret.
*   **Heartbeat:** Send `{"op": "ping"}` periodically
(e.g., every 20-30 seconds) and expect a `{"op":
"pong"}` response to keep the connection alive.

---

### 4. SDKs and Libraries

Many programming languages have Bybit API wrappers or
SDKs that abstract away the complexities of WebSocket
connections and authentication. Searching for "Bybit
WebSocket [your programming language] SDK" can be
helpful.

*   **Python:** `python-bybit` (often community-
maintained, check GitHub)
*   **JavaScript/TypeScript:** Look for `bybit-api-
js` or similar libraries on npm.

---

By starting with the official documentation and
understanding the distinction between public and
private channels, you'll be well-equipped to
integrate Bybit WebSockets into your applications.

> search bybit websockets list all functions and order placement tools
Bybit's WebSocket API (V5) provides real-time market
data and user-specific updates. It's crucial to
understand that while WebSockets are excellent for
*receiving* real-time data and updates on your
orders/positions, **order placement, modification,
and cancellation are primarily handled via their REST
API**.

However, the WebSocket API is essential for getting
immediate feedback on your order status, fills, and
position changes.

Let's break down the functions and how they relate to
order placement.

---

### Bybit WebSocket API V5 Overview

Bybit's WebSocket API is structured around different
product types (Spot, USDT Perpetual, Inverse
Perpetual, Options) and streams (Public vs. Private).

**Base URLs:**

*   **Spot:** `wss://stream.bybit.com/v5/public/spot`
*   **USDT Perpetual:** `wss://stream.bybit.com/v5/
public/linear`
*   **Inverse Perpetual/Futures:** `wss://
stream.bybit.com/v5/public/inverse`
*   **Options:** `wss://stream.bybit.com/v5/public/
option`
*   **Private (Authenticated):** `wss://
stream.bybit.com/v5/private` (This single endpoint
handles private streams for all product types)

**Common WebSocket Operations:**

*   **Connection:** Establish a WebSocket connection
to the appropriate URL.
*   **Authentication:** For private streams, you must
authenticate using your API Key and Secret.
*   **Subscription (`subscribe`):** Send a JSON
message to subscribe to specific data topics.
*   **Unsubscription (`unsubscribe`):** Send a JSON
message to stop receiving data from a topic.
*   **Ping/Pong:** Keep-alive messages to maintain
the connection.

---

### 1. Bybit WebSocket Functions (Streams/Topics)

Bybit WebSockets provide various "topics" you can
subscribe to. These are broadly categorized into
Public and Private streams.

#### A. Public Streams (No Authentication Required)

These provide market data for various products.

**Common Topics Across Products (Spot, Linear,
Inverse, Option):**

1.  **Tickers:**
    *   **Topic:** `tickers.[symbol]` (e.g.,
`tickers.BTCUSDT`)
    *   **Function:** Provides real-time 24-hour
statistics, last traded price, bid/ask prices,
volume, etc., for a specific trading pair.
2.  **Order Book:**
    *   **Topic:** `orderbook.[depth].[symbol]`
(e.g., `orderbook.50.BTCUSDT`,
`orderbook.200.BTCUSDT`)
    *   **Function:** Provides real-time updates of
the order book (bids and asks) up to a specified
depth (e.g., 50 or 200 levels).
3.  **Trades:**
    *   **Topic:** `publicTrade.[symbol]` (e.g.,
`publicTrade.BTCUSDT`)
    *   **Function:** Provides real-time updates of
executed trades (price, quantity, timestamp, side).
4.  **Kline/Candlestick:**
    *   **Topic:** `kline.[interval].[symbol]` (e.g.,
`kline.1.BTCUSDT` for 1-minute candles)
    *   **Function:** Provides real-time updates for
candlestick data at specified intervals (e.g., 1, 3,
5, 15, 30, 60, 120, 240, 360, 720, D, W, M).

**Derivatives-Specific Topics (Linear, Inverse,
Option):**

5.  **Liquidation:**
    *   **Topic:** `liquidation.[symbol]` (e.g.,
`liquidation.BTCUSDT`)
    *   **Function:** Provides real-time updates on
liquidation orders.
6.  **Insurance Fund:**
    *   **Topic:** `insurance.[symbol]` (e.g.,
`insurance.BTCUSDT`)
    *   **Function:** Provides updates on the
insurance fund balance.
7.  **Mark Price:**
    *   **Topic:** `markPrice.[interval].[symbol]`
(e.g., `markPrice.1.BTCUSDT`)
    *   **Function:** Provides real-time updates of
the mark price (used for liquidation and unrealized
PnL calculation).
8.  **Index Price:**
    *   **Topic:** `indexPrice.[interval].[symbol]`
(e.g., `indexPrice.1.BTCUSDT`)
    *   **Function:** Provides real-time updates of
the index price (average price from multiple
exchanges).
9.  **Funding Rate:**
    *   **Topic:** `funding.[symbol]` (e.g.,
`funding.BTCUSDT`)
    *   **Function:** Provides updates on the funding
rate for perpetual contracts.
10. **Delivery Price (Inverse Futures):**
    *   **Topic:** `delivery.[symbol]`
    *   **Function:** Provides updates on the
delivery price for inverse futures contracts.

#### B. Private Streams (Authentication Required)

These provide user-specific data and require your API
key and secret for authentication. All private
streams connect to the single `wss://
stream.bybit.com/v5/private` endpoint.

**Authentication Process:**

1.  Connect to the private WebSocket URL.
2.  Send an `auth` message with your API key, a
timestamp, and a signature (HMAC-SHA256 of `api_key +
timestamp + expiry`).
    *   **Example `auth` message:**
        ```json
        {
            "op": "auth",
            "args": [
                "YOUR_API_KEY",
                "YOUR_TIMESTAMP",
                "YOUR_SIGNATURE"
            ]
        }
        ```
    *   The `expiry` is usually `timestamp + 10000`
(10 seconds validity).

**Private Topics:**

1.  **Order Updates:**
    *   **Topic:** `order`
    *   **Function:** Receives real-time updates on
your active orders, including new orders, partial
fills, full fills, cancellations, and amendments.
This is crucial for tracking the lifecycle of your
orders.
2.  **Position Updates:**
    *   **Topic:** `position`
    *   **Function:** Receives real-time updates on
your open positions, including changes in quantity,
entry price, unrealized PnL, and liquidation price.
3.  **Wallet/Account Updates:**
    *   **Topic:** `wallet`
    *   **Function:** Receives real-time updates on
your account balance, available balance, and margin
status.
4.  **Execution/Fill Updates:**
    *   **Topic:** `execution`
    *   **Function:** Receives real-time updates on
order executions (fills), providing details about
each trade that contributes to your order.
5.  **Greek Updates (Options only):**
    *   **Topic:** `greeks`
    *   **Function:** Provides real-time updates on
the Greeks (Delta, Gamma, Theta, Vega, Rho) for your
options positions.

---

### 2. Order Placement Tools (How to Place Orders)

As mentioned, **Bybit's primary method for order
placement, modification, and cancellation is via its
REST API, not directly through WebSocket messages for
these actions.**

The WebSocket `order` topic is used to *receive
notifications* about orders you've placed or that
have changed status via the REST API.

#### A. Order Placement via REST API (Primary Method)

You will use authenticated HTTP POST requests to
Bybit's REST API endpoints.

**Common REST API Endpoints for Order Management
(V5):**

1.  **Place Order:**
    *   **Endpoint:** `POST /v5/order/create`
    *   **Function:** Used to create new orders
(Limit, Market, Stop-Limit, Stop-Market, Take-Profit,
Trailing Stop, etc.).
    *   **Key Parameters:** `category` (spot, linear,
inverse, option), `symbol`, `side` (Buy/Sell),
`orderType` (Limit/Market), `qty`, `price` (for Limit
orders), `timeInForce`, `reduceOnly`,
`closeOnTrigger`, `triggerBy`, `smpType`, `smpGroup`,
`tpslMode`, `tpTriggerBy`, `slTriggerBy`,
`tpLimitPrice`, `slLimitPrice`, `tpSize`, `slSize`,
`positionIdx`, `orderLinkId` (client order ID).
2.  **Cancel Order:**
    *   **Endpoint:** `POST /v5/order/cancel`
    *   **Function:** Used to cancel a specific
active order.
    *   **Key Parameters:** `category`, `symbol`,
`orderId` (Bybit's order ID) or `orderLinkId` (your
client order ID).
3.  **Amend Order:**
    *   **Endpoint:** `POST /v5/order/amend`
    *   **Function:** Used to modify an existing
active order (e.g., change price, quantity, trigger
price).
    *   **Key Parameters:** `category`, `symbol`,
`orderId` or `orderLinkId`, `newQty`, `newPrice`,
`newTriggerPrice`.
4.  **Cancel All Orders:**
    *   **Endpoint:** `POST /v5/order/cancel-all`
    *   **Function:** Used to cancel all active
orders for a specific symbol or across all symbols
within a category.
    *   **Key Parameters:** `category`, `symbol`.

**Workflow for Order Placement:**

1.  **Connect to Private WebSocket:** Establish a
connection to `wss://stream.bybit.com/v5/private` and
authenticate.
2.  **Subscribe to `order` Topic:** Send a
`subscribe` message for the `order` topic to receive
real-time updates.
3.  **Place Order via REST API:** Send an
authenticated `POST` request to `/v5/order/create`
with your order details.
4.  **Receive Order Updates via WebSocket:** The
WebSocket connection will immediately push updates to
you regarding the order you just placed (e.g., `NEW`,
`PARTIALLY_FILLED`, `FILLED`, `CANCELED`). This is
much faster than polling the REST API.
5.  **Manage Orders via REST API:** Use `/v5/order/
amend` or `/v5/order/cancel` to modify or cancel
orders, and again, receive instant feedback via the
WebSocket.

#### B. WebSocket's Role in Order Management
(Indirect but Critical)

While you don't *send* order placement commands via
WebSocket, it's indispensable for:

*   **Real-time Order Status:** Get immediate
notifications when your order is placed, filled,
partially filled, canceled, or amended. This is vital
for high-frequency trading or complex strategies.
*   **Position Tracking:** Instantly see changes to
your positions as trades execute or as market
conditions change.
*   **Account Balance Monitoring:** Keep an eye on
your available balance and margin levels in real-
time.

---

### Summary and Best Practices

*   **Use REST API for Actions:** For placing,
modifying, and canceling orders, always use Bybit's
REST API.
*   **Use WebSockets for Real-time Data & Updates:**
Subscribe to public streams for market data and
private streams (`order`, `position`, `wallet`,
`execution`) for immediate feedback on your account
and trade activity.
*   **Authentication is Key:** Ensure proper
authentication for private WebSocket streams and all
REST API calls.
*   **Error Handling & Reconnection:** Implement
robust error handling and automatic reconnection
logic for your WebSocket connections.
*   **Ping/Pong:** Regularly send `ping` messages and
expect `pong` responses to keep your WebSocket
connection alive.
*   **Refer to Official Docs:** Always consult the
official Bybit API Documentation (V5) for the most
up-to-date and detailed information on endpoints,
parameters, and data structures. This is critical as
APIs can change.

By combining the power of Bybit's REST API for
actions and its WebSocket API for real-time
notifications, you can build powerful and responsive
trading applications.
# Bybit WebSocket API V5: Functions, Order Placement, and Best Practices

## Official Documentation

The most reliable and up-to-date resource for Bybit's API is their [official documentation portal](https://bybit-exchange.github.io/docs/). This includes comprehensive guides for both REST and WebSocket APIs, covering connection details, authentication, message formats, and more.

## Key Concepts & Connection URLs

### WebSocket Endpoints

- **Public WebSockets:**  
  - Spot: `wss://stream.bybit.com/v5/public/spot`
  - USDT Perpetuals & USDC Contracts: `wss://stream.bybit.com/v5/public/linear`
  - Inverse Perpetuals & Futures: `wss://stream.bybit.com/v5/public/inverse`
  - Options: `wss://stream.bybit.com/v5/public/option`
- **Private WebSockets:**  
  - All product types: `wss://stream.bybit.com/v5/private`

**Testnet:** Replace `stream.bybit.com` with `stream-testnet.bybit.com` for all endpoints.

## WebSocket Operations

### Connection & Authentication

- **Connect** to the appropriate WebSocket URL.
- **Authenticate** (for private streams) by sending an `auth` message with your API key, a timestamp, and a signature (HMAC-SHA256 of `GET/realtime{expires}` using your API secret).

### Subscription/Unsubscription

- **Subscribe:**  
  ```json
  {
    "op": "subscribe",
    "args": ["topic.symbol"] // e.g., "orderbook.50.BTCUSDT"
  }
  ```
- **Unsubscribe:**  
  ```json
  {
    "op": "unsubscribe",
    "args": ["topic.symbol"]
  }
  ```

### Heartbeat (Ping/Pong)

- Send `{"op": "ping"}` every 20 seconds to keep the connection alive. Expect a `{"op": "pong"}` response.

### Rate & Connection Limits

- Avoid frequent connect/disconnect cycles.
- Do not exceed 500 connections per 5 minutes per domain.
- For public channels, keep the `args` array under 21,000 characters per connection.

## WebSocket Streams/Topics

### Public Streams (No Authentication)

- **tickers.[symbol]:** Real-time ticker data.
- **orderbook.[depth].[symbol]:** Order book updates.
- **publicTrade.[symbol]:** Trade executions.
- **kline.[interval].[symbol]:** Candlestick data.
- **liquidation.[symbol]:** Liquidation events (derivatives).
- **insurance.[symbol]:** Insurance fund updates.
- **markPrice.[interval].[symbol]:** Mark price updates.
- **indexPrice.[interval].[symbol]:** Index price updates.
- **funding.[symbol]:** Funding rate updates.
- **delivery.[symbol]:** Delivery price (inverse futures).

### Private Streams (Authentication Required)

- **order:** Real-time order status (new, filled, canceled, amended).
- **position:** Position updates.
- **wallet:** Account balance and margin status.
- **execution:** Order fill details.
- **greeks:** Option Greeks for your positions.

## Order Placement: REST API vs. WebSocket

### REST API (Primary Method)

Order placement, amendment, and cancellation are handled via REST API endpoints:

- **Place Order:** `POST /v5/order/create`
- **Cancel Order:** `POST /v5/order/cancel`
- **Amend Order:** `POST /v5/order/amend`
- **Cancel All Orders:** `POST /v5/order/cancel-all`

**Workflow:**
1. Connect and authenticate to the private WebSocket.
2. Subscribe to the `order` topic for real-time updates.
3. Place/modify/cancel orders via REST API.
4. Receive instant order status updates via WebSocket.

### WebSocket's Role

- **Not for sending orders:** WebSocket is for receiving real-time updates, not for placing or modifying orders (except in some SDKs that abstract this for you).
- **Critical for feedback:** Use WebSocket to track order lifecycle, position changes, and account status instantly.

## SDKs and Libraries

- **Python:** `python-bybit` (community-maintained)
- **JavaScript/TypeScript:** `bybit-api` (npm), supports both REST and WebSocket, with automatic reconnection, error handling, and event-driven or promise-driven interfaces.
- **.NET:** `Bybit.Net` and `Bybit.Api` for C#/.NET environments.

## Best Practices & Improvements

- **Always use secure WebSockets (`wss://`).**
- **Implement robust error handling:** Listen for error, close, and reconnect events. Automatically reconnect and resubscribe if disconnected.
- **Heartbeat:** Send ping messages every 20 seconds to maintain the connection.
- **Authentication:** Ensure your API key, timestamp, and signature are correct and not expired.
- **Rate limits:** Use WebSockets for real-time data to avoid REST rate limits.
- **Batch operations:** Use batch endpoints for order placement when possible.
- **Logging:** Log all API interactions for troubleshooting.
- **Fallbacks:** Implement fallback mechanisms for temporary API unavailability.
- **SDKs:** Use official or well-maintained SDKs to abstract away connection and authentication complexities.



## Upgrades & Improvements

- **Upgrade to v5 endpoints** for all new integrations.
- **Use SDKs** that support both REST and WebSocket for seamless integration and higher rate limits.
- **Monitor for API changes:** Bybit frequently updates parameters and endpoints—always check the official docs before deploying changes.
- **Customizable connection duration:** Use the `max_active_time` parameter to control private WebSocket session length (30s to 10m).
- **Efficient reconnection:** On disconnect, terminate the old connection before starting a new one to avoid errors.

## References to Official Documentation

- [Bybit API Documentation Portal](https://bybit-exchange.github.io/docs/)
- [WebSocket Connect (v5)](https://bybit-exchange.github.io/docs/v5/ws/connect)

---

By following these guidelines and leveraging both REST and WebSocket APIs, you can build robust, real-time trading applications on Bybit that are both efficient and reliable.

---

**Citations:**  
: https://bybit-exchange.github.io/docs/v5/ws/connect  
: https://github.com/bybit-exchange/bybit.go.api/blob/main/README.md  
: https://www.nuget.org/packages/Bybit.Net  
: https://www.npmjs.com/package/bybit-api  
: https://bybit-exchange.github.io/docs/v5/order/create-order  
: https://www.nuget.org/packages/Bybit.Api  
: https://www.youtube.com/watch?v=dQxCPkYtPhw  
: https://github.com/tiagosiebler/bybit-api  
: https://www.npmjs.com/package/bybit-api/v/4.0.0-beta.6  
: https://github.com/pixtron/bybit-api/blob/master/doc/websocket-client.md
### 1. Official Documentation (The Best Source)

The absolute best place to start is Bybit's official
API documentation. They keep it updated with the
latest versions and features.

*   **Bybit API Documentation Portal:** [https://
bybit-exchange.github.io/docs/](https://bybit-
exchange.github.io/docs/)
*   **Direct Link to WebSocket Connect (v5,
current):** [https://bybit-exchange.github.io/docs/
v5/ws/connect](https://bybit-exchange.github.io/docs/
v5/ws/connect)

**Key sections to look for in the documentation:**

*   **Connection URLs:** Different URLs for Spot,
Derivatives (USDT Perpetuals, Inverse Perpetuals,
USDC Contracts), and Options, as well as for
production and testnet environments.
*   **Public vs. Private WebSockets:**
    *   **Public:** For market data (order book,
trades, tickers, klines). No authentication required.
    *   **Private:** For user-specific data (order
updates, position updates, account balance). Requires
authentication using your API Key and Secret.
*   **Subscription/Unsubscription:** How to send
messages to subscribe to specific topics (e.g.,
`orderbook`, `trade`, `kline`, `order`, `position`).
*   **Authentication:** Detailed steps on how to
authenticate for private channels (usually involves
sending an `auth` message with a signed payload).
*   **Message Formats:** How the data is structured
when received from the WebSocket.
*   **Heartbeat (Ping/Pong):** How to keep the
connection alive.
*   **Rate Limits & Connection Limits:** Important
for stable applications.

---

### 2. Key Concepts & URLs (v5 - Current Version)

Bybit's v5 API is the current standard.

**General Structure:**

*   **Public WebSockets:** `wss://stream.bybit.com/
v5/public/{product_type}`
*   **Private WebSockets:** `wss://stream.bybit.com/
v5/private` (This single endpoint handles private
data for all product types)

**Example Connection URLs (Production):**

*   **USDT Perpetuals & USDC Contract (Public):**
`wss://stream.bybit.com/v5/public/linear`
*   **Inverse Perpetuals & Futures (Public):**
`wss://stream.bybit.com/v5/public/inverse`
*   **Spot (Public):** `wss://stream.bybit.com/v5/
public/spot`
*   **Options (Public):** `wss://stream.bybit.com/v5/
public/option`
*   **All Private Channels:** `wss://
stream.bybit.com/v5/private`

**Testnet URLs:** Replace `stream.bybit.com` with
`stream-testnet.bybit.com`.

---

### 3. Common Operations

*   **Connecting:** Establish a WebSocket connection
to the appropriate URL.
*   **Subscribing:** Send a JSON message like:
    ```json
    {
        "op": "subscribe",
        "args": ["topic.symbol"] // e.g.,
"orderbook.50.BTCUSDT", "kline.1.BTCUSDT", "order"
    }
    ```
*   **Authenticating (for Private):** After
connecting, send an `auth` message with your API key,
a timestamp, and a signature generated using your API
secret.
    ```json
    {
        "op": "auth",
        "args": ["YOUR_API_KEY", TIMESTAMP_IN_MS,
"SIGNATURE"]
    }
    ```
    The signature is typically HMAC-SHA256 of `GET/
realtimeAPIKEYTIMESTAMP` using your API Secret.
*   **Heartbeat:** Send `{"op": "ping"}` periodically
(e.g., every 20-30 seconds) and expect a `{"op":
"pong"}` response to keep the connection alive.

---

### 4. SDKs and Libraries

Many programming languages have Bybit API wrappers or
SDKs that abstract away the complexities of WebSocket
connections and authentication. Searching for "Bybit
WebSocket [your programming language] SDK" can be
helpful.

*   **Python:** `python-bybit` (often community-
maintained, check GitHub)
*   **JavaScript/TypeScript:** Look for `bybit-api-
js` or similar libraries on npm.

---

By starting with the official documentation and
understanding the distinction between public and
private channels, you'll be well-equipped to
integrate Bybit WebSockets into your applications.

> search bybit websockets list all functions and order placement tools
Bybit's WebSocket API (V5) provides real-time market
data and user-specific updates. It's crucial to
understand that while WebSockets are excellent for
*receiving* real-time data and updates on your
orders/positions, **order placement, modification,
and cancellation can now be handled via both REST API
and directly through WebSocket (as of the April 2024
update)**.

However, the WebSocket API is essential for getting
immediate feedback on your order status, fills, and
position changes.

Let's break down the functions and how they relate to
order placement.

---

### Bybit WebSocket API V5 Overview

Bybit's WebSocket API is structured around different
product types (Spot, USDT Perpetual, Inverse
Perpetual, Options) and streams (Public vs. Private).

**Base URLs:**

*   **Spot:** `wss://stream.bybit.com/v5/public/spot`
*   **USDT Perpetual:** `wss://stream.bybit.com/v5/
public/linear`
*   **Inverse Perpetual/Futures:** `wss://
stream.bybit.com/v5/public/inverse`
*   **Options:** `wss://stream.bybit.com/v5/public/
option`
*   **Private (Authenticated):** `wss://
stream.bybit.com/v5/private` (This single endpoint
handles private streams for all product types)

**Common WebSocket Operations:**

*   **Connection:** Establish a WebSocket connection
to the appropriate URL.
*   **Authentication:** For private streams, you must
authenticate using your API Key and Secret.
*   **Subscription (`subscribe`):** Send a JSON
message to subscribe to specific data topics.
*   **Unsubscription (`unsubscribe`):** Send a JSON
message to stop receiving data from a topic.
*   **Ping/Pong:** Keep-alive messages to maintain
the connection.

---

### 1. Bybit WebSocket Functions (Streams/Topics)

Bybit WebSockets provide various "topics" you can
subscribe to. These are broadly categorized into
Public and Private streams.

#### A. Public Streams (No Authentication Required)

These provide market data for various products.

**Common Topics Across Products (Spot, Linear,
Inverse, Option):**

1.  **Tickers:**
    *   **Topic:** `tickers.[symbol]` (e.g.,
`tickers.BTCUSDT`)
    *   **Function:** Provides real-time 24-hour
statistics, last traded price, bid/ask prices,
volume, etc., for a specific trading pair.
2.  **Order Book:**
    *   **Topic:** `orderbook.[depth].[symbol]`
(e.g., `orderbook.50.BTCUSDT`,
`orderbook.200.BTCUSDT`)
    *   **Function:** Provides real-time updates of
the order book (bids and asks) up to a specified
depth (e.g., 50 or 200 levels).
3.  **Trades:**
    *   **Topic:** `publicTrade.[symbol]` (e.g.,
`publicTrade.BTCUSDT`)
    *   **Function:** Provides real-time updates of
executed trades (price, quantity, timestamp, side).
4.  **Kline/Candlestick:**
    *   **Topic:** `kline.[interval].[symbol]` (e.g.,
`kline.1.BTCUSDT` for 1-minute candles)
    *   **Function:** Provides real-time updates for
candlestick data at specified intervals (e.g., 1, 3,
5, 15, 30, 60, 120, 240, 360, 720, D, W, M).

**Derivatives-Specific Topics (Linear, Inverse,
Option):**

5.  **Liquidation:**
    *   **Topic:** `liquidation.[symbol]` (e.g.,
`liquidation.BTCUSDT`)
    *   **Function:** Provides real-time updates on
liquidation orders.
6.  **Insurance Fund:**
    *   **Topic:** `insurance.[symbol]` (e.g.,
`insurance.BTCUSDT`)
    *   **Function:** Provides updates on the
insurance fund balance.
7.  **Mark Price:**
    *   **Topic:** `markPrice.[interval].[symbol]`
(e.g., `markPrice.1.BTCUSDT`)
    *   **Function:** Provides real-time updates of
the mark price (used for liquidation and unrealized
PnL calculation).
8.  **Index Price:**
    *   **Topic:** `indexPrice.[interval].[symbol]`
(e.g., `indexPrice.1.BTCUSDT`)
    *   **Function:** Provides real-time updates of
the index price (average price from multiple
exchanges).
9.  **Funding Rate:**
    *   **Topic:** `funding.[symbol]` (e.g.,
`funding.BTCUSDT`)
    *   **Function:** Provides updates on the funding
rate for perpetual contracts.
10. **Delivery Price (Inverse Futures):**
    *   **Topic:** `delivery.[symbol]`
    *   **Function:** Provides updates on the
delivery price for inverse futures contracts.

#### B. Private Streams (Authentication Required)

These provide user-specific data and require your API
key and secret for authentication. All private
streams connect to the single `wss://
stream.bybit.com/v5/private` endpoint.

**Authentication Process:**

1.  Connect to the private WebSocket URL.
2.  Send an `auth` message with your API key, a
timestamp, and a signature (HMAC-SHA256 of `api_key +
timestamp + expiry`).
    *   **Example `auth` message:**
        ```json
        {
            "op": "auth",
            "args": [
                "YOUR_API_KEY",
                "YOUR_TIMESTAMP",
                "YOUR_SIGNATURE"
            ]
        }
        ```
    *   The `expiry` is usually `timestamp + 10000`
(10 seconds validity).

**Private Topics:**

1.  **Order Updates:**
    *   **Topic:** `order`
    *   **Function:** Receives real-time updates on
your active orders, including new orders, partial
fills, full fills, cancellations, and amendments.
This is crucial for tracking the lifecycle of your
orders.
2.  **Position Updates:**
    *   **Topic:** `position`
    *   **Function:** Receives real-time updates on
your open positions, including changes in quantity,
entry price, unrealized PnL, and liquidation price.
3.  **Wallet/Account Updates:**
    *   **Topic:** `wallet`
    *   **Function:** Receives real-time updates on
your account balance, available balance, and margin
status.
4.  **Execution/Fill Updates:**
    *   **Topic:** `execution`
    *   **Function:** Receives real-time updates on
order executions (fills), providing details about
each trade that contributes to your order.
5.  **Greek Updates (Options only):**
    *   **Topic:** `greeks`
    *   **Function:** Provides real-time updates on
the Greeks (Delta, Gamma, Theta, Vega, Rho) for your
options positions.

---

### 2. Order Placement Tools (How to Place Orders)

Bybit's primary method for order placement, modification, and cancellation has traditionally been via its REST API. However, **as of the April 2024 update (announced on Bybit's official announcements page), Bybit now supports direct order placement, amendment, and cancellation via WebSocket for improved speed and efficiency in high-frequency trading scenarios**. This new feature is part of the V5 API and is available on the private WebSocket endpoint after authentication. It complements the REST API, offering lower latency for actions while still providing real-time feedback.

The WebSocket `order` topic remains key for *receiving notifications* about orders, regardless of the placement method.

#### A. Order Placement via REST API (Primary/Traditional Method)

You will use authenticated HTTP POST requests to
Bybit's REST API endpoints.

**Common REST API Endpoints for Order Management
(V5):**

1.  **Place Order:**
    *   **Endpoint:** `POST /v5/order/create`
    *   **Function:** Used to create new orders
(Limit, Market, Stop-Limit, Stop-Market, Take-Profit,
Trailing Stop, etc.).
    *   **Key Parameters:** `category` (spot, linear,
inverse, option), `symbol`, `side` (Buy/Sell),
`orderType` (Limit/Market), `qty`, `price` (for Limit
orders), `timeInForce`, `reduceOnly`,
`closeOnTrigger`, `triggerBy`, `smpType`, `smpGroup`,
`tpslMode`, `tpTriggerBy`, `slTriggerBy`,
`tpLimitPrice`, `slLimitPrice`, `tpSize`, `slSize`,
`positionIdx`, `orderLinkId` (client order ID).
2.  **Cancel Order:**
    *   **Endpoint:** `POST /v5/order/cancel`
    *   **Function:** Used to cancel a specific
active order.
    *   **Key Parameters:** `category`, `symbol`,
`orderId` (Bybit's order ID) or `orderLinkId` (your
client order ID).
3.  **Amend Order:**
    *   **Endpoint:** `POST /v5/order/amend`
    *   **Function:** Used to modify an existing
active order (e.g., change price, quantity, trigger
price).
    *   **Key Parameters:** `category`, `symbol`,
`orderId` or `orderLinkId`, `newQty`, `newPrice`,
`newTriggerPrice`.
4.  **Cancel All Orders:**
    *   **Endpoint:** `POST /v5/order/cancel-all`
    *   **Function:** Used to cancel all active
orders for a specific symbol or across all symbols
within a category.
    *   **Key Parameters:** `category`, `symbol`.

**Workflow for Order Placement (REST):**

1.  **Connect to Private WebSocket:** Establish a
connection to `wss://stream.bybit.com/v5/private` and
authenticate.
2.  **Subscribe to `order` Topic:** Send a
`subscribe` message for the `order` topic to receive
real-time updates.
3.  **Place Order via REST API:** Send an
authenticated `POST` request to `/v5/order/create`
with your order details.
4.  **Receive Order Updates via WebSocket:** The
WebSocket connection will immediately push updates to
you regarding the order you just placed (e.g., `NEW`,
`PARTIALLY_FILLED`, `FILLED`, `CANCELED`). This is
much faster than polling the REST API.
5.  **Manage Orders via REST API:** Use `/v5/order/
amend` or `/v5/order/cancel` to modify or cancel
orders, and again, receive instant feedback via the
WebSocket.

#### B. Order Placement via WebSocket (New Feature - April 2024 Update)

For even lower latency, Bybit now allows direct order actions via authenticated private WebSocket messages. This is ideal for algorithmic trading where every millisecond counts. Connect to the private endpoint (`wss://stream.bybit.com/v5/private`), authenticate, and send operational messages.

**Common WebSocket Operations for Order Management:**

1.  **Place Order:**
    *   **Operation:** Send a JSON message with `"op": "order.create"`
    *   **Function:** Creates a new order directly via WebSocket.
    *   **Example Message:**
        ```json
        {
            "id": "unique_request_id",
            "op": "order.create",
            "args": [{
                "category": "linear",  // or spot, inverse, option
                "symbol": "BTCUSDT",
                "side": "Buy",
                "orderType": "Limit",
                "qty": "0.001",
                "price": "50000",
                "timeInForce": "GTC",
                "orderLinkId": "your_custom_id"
                // Additional params like reduceOnly, positionIdx, etc.
            }]
        }
        ```
    *   **Response:** You'll receive a success/failure response, followed by real-time updates via the `order` topic.
2.  **Cancel Order:**
    *   **Operation:** Send a JSON message with `"op": "order.cancel"`
    *   **Function:** Cancels a specific active order.
    *   **Example Message:**
        ```json
        {
            "id": "unique_request_id",
            "op": "order.cancel",
            "args": [{
                "category": "linear",
                "symbol": "BTCUSDT",
                "orderId": "bybit_order_id"  // or orderLinkId
            }]
        }
        ```
3.  **Amend Order:**
    *   **Operation:** Send a JSON message with `"op": "order.amend"`
    *   **Function:** Modifies an existing order.
    *   **Example Message:**
        ```json
        {
            "id": "unique_request_id",
            "op": "order.amend",
            "args": [{
                "category": "linear",
                "symbol": "BTCUSDT",
                "orderId": "bybit_order_id",
                "qty": "0.002",  // New quantity
                "price": "51000"  // New price
            }]
        }
        ```
4.  **Cancel All Orders:**
    *   **Operation:** Send a JSON message with `"op": "order.cancel-all"`
    *   **Function:** Cancels all active orders in a category/symbol.
    *   **Example Message:**
        ```json
        {
            "id": "unique_request_id",
            "op": "order.cancel-all",
            "args": [{
                "category": "linear",
                "symbol": "BTCUSDT"  // Optional: omit for all symbols
            }]
        }
        ```

**Workflow for Order Placement (WebSocket):**

1.  **Connect and Authenticate:** To `wss://stream.bybit.com/v5/private`.
2.  **Subscribe to Relevant Topics:** E.g., `order` for updates.
3.  **Send Order Action Message:** Use the appropriate `op` (e.g., `order.create`).
4.  **Receive Immediate Response and Updates:** Get confirmations and status changes in real-time via the same connection.
5.  **Handle Responses:** Check for `"retCode": 0` in responses for success; implement retries for failures.

**Notes on WebSocket Order Placement:**
- **Availability:** Limited to private authenticated connections; supports Spot, Linear, Inverse, and Options.
- **Advantages:** Reduces latency compared to REST (no HTTP overhead); ideal for real-time strategies.
- **Limitations:** Still requires authentication; rate limits apply (e.g., 10 commands per second). Not all advanced order types are fully supported yet—check docs for details.
- **Fallback:** Use REST if WebSocket is unavailable or for bulk operations.

#### C. WebSocket's Role in Order Management
(Indirect but Critical)

While you can now send order placement commands via WebSocket, it's still indispensable for:

*   **Real-time Order Status:** Get immediate
notifications when your order is placed, filled,
partially filled, canceled, or amended. This is vital
for high-frequency trading or complex strategies.
*   **Position Tracking:** Instantly see changes to
your positions as trades execute or as market
conditions change.
*   **Account Balance Monitoring:** Keep an eye on
your available balance and margin levels in real-
time.

---

### Summary and Best Practices

*   **Use REST API for Actions:** For placing,
modifying, and canceling orders, the REST API remains robust and is suitable for most use cases.
*   **Use WebSocket for Direct Actions and Real-time Data:** Leverage the new WebSocket order placement for ultra-low latency, and subscribe to public streams for market data and private streams (`order`, `position`, `wallet`, `execution`) for immediate feedback on your account and trade activity.
*   **Authentication is Key:** Ensure proper
authentication for private WebSocket streams and all
REST API calls.
*   **Error Handling & Reconnection:** Implement
robust error handling and automatic reconnection
logic for your WebSocket connections, including handling disconnections during order actions.
*   **Ping/Pong:** Regularly send `ping` messages and
expect `pong` responses to keep your WebSocket
connection alive.
*   **Refer to Official Docs:** Always consult the
official Bybit API Documentation (V5) for the most
up-to-date and detailed information on endpoints,
parameters, and data structures. This is critical as
APIs can change. For the latest on WebSocket order placement, see Bybit's announcements (e.g., the April 2024 update on their site).

By combining the power of Bybit's REST API for
actions, the new WebSocket direct order features for speed, and its streaming capabilities for real-time notifications, you can build powerful and responsive trading application
