
Here are 20 `gemini-cli` pipes designed to interact with the Bybit V5 API.

**Prerequisites:**

1.  **Gemini-CLI Installed:** Make sure you have `gemini-cli` installed and configured.
2.  **Bybit API Keys:** You'll need your Bybit V5 API Key and Secret. These are typically set as environment variables `BYBIT_API_KEY` and `BYBIT_API_SECRET` or configured in your `gemini-cli` profile.
3.  **Understanding Bybit V5 Categories:** Many Bybit V5 endpoints require a `category` parameter (e.g., `spot`, `linear`, `inverse`). This is crucial for distinguishing between markets.

---

### Bybit V5 API Pipes for Gemini-CLI

Each pipe includes its name, a brief description, the Bybit V5 API endpoint it targets, common parameters, and an example usage.

---

#### **Market Data & Public Information**

1.  **`bybit-v5-server-time`**
    *   **Description:** Get the current Bybit server time. Useful for checking API connectivity and time synchronization.
    *   **Bybit V5 Endpoint:** `/v5/market/time`
    *   **Common Parameters:** None
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-server-time
        ```

2.  **`bybit-v5-instruments-info`**
    *   **Description:** Get information on all available trading instruments (symbols).
    *   **Bybit V5 Endpoint:** `/v5/market/instruments-info`
    *   **Common Parameters:** `category` (required: `spot`, `linear`, `inverse`, `option`), `symbol` (optional), `limit`, `cursor`
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-instruments-info --category linear --symbol BTCUSDT
        gemini pipe bybit-v5-instruments-info --category spot --limit 10
        ```

3.  **`bybit-v5-ticker`**
    *   **Description:** Get the latest ticker information for one or all instruments in a category.
    *   **Bybit V5 Endpoint:** `/v5/market/tickers`
    *   **Common Parameters:** `category` (required: `spot`, `linear`, `inverse`, `option`), `symbol` (optional)
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-ticker --category linear --symbol ETHUSDT
        gemini pipe bybit-v5-ticker --category spot
        ```

4.  **`bybit-v5-orderbook`**
    *   **Description:** Get the orderbook data for a specific instrument.
    *   **Bybit V5 Endpoint:** `/v5/market/orderbook`
    *   **Common Parameters:** `category` (required), `symbol` (required), `limit` (default 1, max 50 for spot, 200 for derivatives)
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-orderbook --category linear --symbol SOLUSDT --limit 25
        ```

5.  **`bybit-v5-klines`**
    *   **Description:** Get candlestick data (Kline) for an instrument.
    *   **Bybit V5 Endpoint:** `/v5/market/kline`
    *   **Common Parameters:** `category` (required), `symbol` (required), `interval` (required: e.g., "1", "5", "60", "D"), `start`, `end`, `limit`
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-klines --category spot --symbol BTCUSDT --interval 60 --limit 100
        ```

6.  **`bybit-v5-public-trades`**
    *   **Description:** Get recent public trade data for an instrument.
    *   **Bybit V5 Endpoint:** `/v5/market/recent-trade`
    *   **Common Parameters:** `category` (required), `symbol` (required), `limit`
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-public-trades --category linear --symbol BTCUSDT --limit 50
        ```

7.  **`bybit-v5-funding-rate-history`**
    *   **Description:** Get historical funding rate data for derivatives.
    *   **Bybit V5 Endpoint:** `/v5/market/funding/history`
    *   **Common Parameters:** `category` (required: `linear`, `inverse`), `symbol` (required), `limit`
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-funding-rate-history --category linear --symbol BTCUSDT --limit 10
        ```

---

#### **Account & Wallet Management**

8.  **`bybit-v5-wallet-balance`**
    *   **Description:** Get account wallet balance for a specific coin or all coins under a unified account.
    *   **Bybit V5 Endpoint:** `/v5/account/wallet-balance`
    *   **Common Parameters:** `accountType` (required: `UNIFIED_MARGIN`, `CONTRACT`, `SPOT`), `coin` (optional)
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-wallet-balance --accountType UNIFIED_MARGIN --coin USDT
        gemini pipe bybit-v5-wallet-balance --accountType UNIFIED_MARGIN
        ```

9.  **`bybit-v5-asset-info`**
    *   **Description:** Get information on supported assets/coins, including chain details.
    *   **Bybit V5 Endpoint:** `/v5/asset/coin/query-info`
    *   **Common Parameters:** `coin` (optional)
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-asset-info --coin BTC
        gemini pipe bybit-v5-asset-info
        ```

10. **`bybit-v5-deposit-history`**
    *   **Description:** Get deposit records for your account.
    *   **Bybit V5 Endpoint:** `/v5/asset/deposit/query-record`
    *   **Common Parameters:** `coin` (optional), `limit`, `startTime`, `endTime`
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-deposit-history --coin USDT --limit 50
        ```

11. **`bybit-v5-withdrawal-history`**
    *   **Description:** Get withdrawal records for your account.
    *   **Bybit V5 Endpoint:** `/v5/asset/withdraw/query-record`
    *   **Common Parameters:** `coin` (optional), `limit`, `startTime`, `endTime`
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-withdrawal-history --coin BTC --limit 20
        ```

---

#### **Trading - Spot**

12. **`bybit-v5-spot-place-order`**
    *   **Description:** Place a new spot order.
    *   **Bybit V5 Endpoint:** `/v5/order/create`
    *   **Common Parameters:** `category` (must be `spot`), `symbol`, `side` (Buy/Sell), `orderType` (Limit/Market), `qty`, `price` (for Limit orders)
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-spot-place-order --symbol BTCUSDT --side Buy --orderType Limit --qty 0.001 --price 60000
        gemini pipe bybit-v5-spot-place-order --symbol ETHUSDT --side Sell --orderType Market --qty 0.01
        ```

13. **`bybit-v5-spot-cancel-order`**
    *   **Description:** Cancel an existing spot order.
    *   **Bybit V5 Endpoint:** `/v5/order/cancel`
    *   **Common Parameters:** `category` (must be `spot`), `symbol`, `orderId` (or `clientOrderId`)
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-spot-cancel-order --symbol BTCUSDT --orderId 1234567890
        ```

14. **`bybit-v5-spot-open-orders`**
    *   **Description:** Get a list of open spot orders.
    *   **Bybit V5 Endpoint:** `/v5/order/realtime`
    *   **Common Parameters:** `category` (must be `spot`), `symbol` (optional), `limit`
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-spot-open-orders --symbol ETHUSDT --limit 10
        ```

15. **`bybit-v5-spot-order-history`**
    *   **Description:** Get historical spot orders.
    *   **Bybit V5 Endpoint:** `/v5/order/history`
    *   **Common Parameters:** `category` (must be `spot`), `symbol` (optional), `limit`, `startTime`, `endTime`
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-spot-order-history --symbol BTCUSDT --limit 50
        ```

---

#### **Trading - Derivatives (Linear/Inverse)**

16. **`bybit-v5-derivatives-place-order`**
    *   **Description:** Place a new derivatives order (Linear or Inverse).
    *   **Bybit V5 Endpoint:** `/v5/order/create`
    *   **Common Parameters:** `category` (required: `linear`, `inverse`), `symbol`, `side`, `orderType`, `qty`, `price` (for Limit), `reduceOnly`, `closeOnTrigger`, `positionIdx`
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-derivatives-place-order --category linear --symbol BTCUSDT --side Sell --orderType Market --qty 0.01 --reduceOnly true
        gemini pipe bybit-v5-derivatives-place-order --category linear --symbol ETHUSDT --side Buy --orderType Limit --qty 0.1 --price 3000
        ```

17. **`bybit-v5-derivatives-cancel-order`**
    *   **Description:** Cancel an existing derivatives order.
    *   **Bybit V5 Endpoint:** `/v5/order/cancel`
    *   **Common Parameters:** `category` (required: `linear`, `inverse`), `symbol`, `orderId` (or `clientOrderId`)
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-derivatives-cancel-order --category linear --symbol ETHUSDT --orderId 987654321
        ```

18. **`bybit-v5-derivatives-open-orders`**
    *   **Description:** Get a list of open derivatives orders.
    *   **Bybit V5 Endpoint:** `/v5/order/realtime`
    *   **Common Parameters:** `category` (required: `linear`, `inverse`), `symbol` (optional), `limit`
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-derivatives-open-orders --category linear --symbol SOLUSDT
        ```

19. **`bybit-v5-position-info`**
    *   **Description:** Get current position details for derivatives.
    *   **Bybit V5 Endpoint:** `/v5/position/list`
    *   **Common Parameters:** `category` (required: `linear`, `inverse`), `symbol` (optional)
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-position-info --category linear --symbol BTCUSDT
        gemini pipe bybit-v5-position-info --category linear # Get all linear positions
        ```

20. **`bybit-v5-set-leverage`**
    *   **Description:** Set the leverage for a derivatives symbol.
    *   **Bybit V5 Endpoint:** `/v5/position/set-leverage`
    *   **Common Parameters:** `category` (required: `linear`, `inverse`), `symbol` (required), `buyLeverage` (required), `sellLeverage` (required)
    *   **Example Usage:**
        ```bash
        gemini pipe bybit-v5-set-leverage --category linear --symbol ETHUSDT --buyLeverage 10 --sellLeverage 10
        ```

---

**Important Notes:**

*   **API Key and Secret:** Ensure your Bybit API Key and Secret are correctly configured in `gemini-cli` or as environment variables. These pipes will fail without proper authentication for private endpoints.
*   **Rate Limits:** Be mindful of Bybit's API rate limits. Excessive requests can lead to temporary bans.
*   **Parameter Validation:** The examples provide common parameters. Always refer to the official Bybit V5 API documentation for a complete list of parameters, their types, and valid values for each endpoint.
*   **Error Handling:** `gemini-cli` will typically output the raw JSON response, including any errors from the Bybit API. Check the output for `retCode` and `retMsg` in case of issues.
*   **Security:** Never hardcode your API keys directly into scripts. Use environment


# ~/.gemini/pipes.yaml or a dedicated file imported into your config

pipes:

  # --- Market Data Pipes (6) ---

  get-kline:
    description: Retrieves candlestick data for a given symbol and interval.
    input:
      symbol: { type: string, required: true, description: "Trading pair, e.g., BTCUSDT" }
      interval: { type: string, required: true, description: "Interval, e.g., 1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M" }
      start_time: { type: integer, description: "Start time in milliseconds (optional)" }
      end_time: { type: integer, description: "End time in milliseconds (optional)" }
      limit: { type: integer, default: 200, description: "Limit for data size, max 1000" }
      category: { type: string, default: "linear", description: "Product category (spot, linear, inverse)" }
    output:
      type: json
    transform:
      - jq: '.result.list[] | {timestamp: (.[0] | tonumber | strftime("%Y-%m-%d %H:%M:%S")), open: .[1], high: .[2], low: .[3], close: .[4], volume: .[5], turnover: .[6]}'
    exec:
      plugin: bybit-v5
      method: market.getKline

  get-ticker:
    description: Retrieves the latest ticker information for a symbol or all symbols.
    input:
      category: { type: string, required: true, description: "Product category (spot, linear, inverse, option)" }
      symbol: { type: string, description: "Trading pair, e.g., BTCUSDT (optional, for all if omitted)" }
    output:
      type: json
    transform:
      - jq: '.result.list[] | {symbol: .symbol, lastPrice: .lastPrice, high24h: .highPrice24h, low24h: .lowPrice24h, turnover24h: .turnover24h}'
    exec:
      plugin: bybit-v5
      method: market.getTickers

  get-orderbook:
    description: Retrieves the orderbook for a given symbol.
    input:
      category: { type: string, required: true, description: "Product category (spot, linear, inverse, option)" }
      symbol: { type: string, required: true, description: "Trading pair, e.g., BTCUSDT" }
      limit: { type: integer, default: 25, description: "Limit for data size, max 50" }
    output:
      type: json
    transform:
      - jq: '{symbol: .result.s, bids: .result.bids, asks: .result.asks}'
    exec:
      plugin: bybit-v5
      method: market.getOrderbook

  get-recent-trades:
    description: Retrieves the latest public trading data for a symbol.
    input:
      category: { type: string, required: true, description: "Product category (spot, linear, inverse, option)" }
      symbol: { type: string, required: true, description: "Trading pair, e.g., BTCUSDT" }
      limit: { type: integer, default: 50, description: "Limit for data size, max 1000" }
    output:
      type: json
    transform:
      - jq: '.result.list[] | {timestamp: (.time | tonumber | strftime("%Y-%m-%d %H:%M:%S")), price: .price, qty: .qty, side: .side}'
    exec:
      plugin: bybit-v5
      method: market.getRecentTrades

  get-instruments-info:
    description: Retrieves instrument information for a product category.
    input:
      category: { type: string, required: true, description: "Product category (spot, linear, inverse, option)" }
      symbol: { type: string, description: "Trading pair, e.g., BTCUSDT (optional, for all if omitted)" }
      limit: { type: integer, default: 50, description: "Limit for data size, max 1000" }
    output:
      type: json
    transform:
      - jq: '.result.list[] | {symbol: .symbol, contractType: .contractType, status: .status, baseCoin: .baseCoin, quoteCoin: .quoteCoin}'
    exec:
      plugin: bybit-v5
      method: market.getInstrumentsInfo

  get-funding-rate:
    description: Retrieves the historical funding rate for a symbol (linear/inverse).
    input:
      category: { type: string, required: true, description: "Product category (linear, inverse)" }
      symbol: { type: string, required: true, description: "Trading pair, e.g., BTCUSDT" }
      limit: { type: integer, default: 20, description: "Limit for data size, max 200" }
    output:
      type: json
    transform:
      - jq: '.result.list[] | {symbol: .symbol, fundingRate: .fundingRate, fundingTime: (.fundingRateTimestamp | tonumber | strftime("%Y-%m-%d %H:%M:%S"))}'
    exec:
      plugin: bybit-v5
      method: market.getFundingRateHistory

  # --- Account & Wallet Pipes (4) ---

  get-wallet-balance:
    description: Retrieves wallet balance information for a specific account type.
    input:
      account_type: { type: string, default: "UNIFIED", description: "Account type (SPOT, UNIFIED, CLASSIC)" }
      coin: { type: string, description: "Coin to filter by, e.g., BTC, USDT (optional)" }
    output:
      type: json
    transform:
      - jq: '.result.list[] | {accountType: .accountType, totalEquity: .totalEquity, totalWalletBalance: .totalWalletBalance, unrealisedPNL: .unrealisedPNL, coins: .coin}'
    exec:
      plugin: bybit-v5
      method: account.getWalletBalance

  get-positions:
    description: Retrieves current open positions.
    input:
      category: { type: string, required: true, description: "Product category (linear, inverse, option)" }
      symbol: { type: string, description: "Trading pair, e.g., BTCUSDT (optional)" }
    output:
      type: json
    transform:
      - jq: '.result.list[] | {symbol: .symbol, side: .side, size: .size, entryPrice: .avgPrice, liqPrice: .liqPrice, unrealizedPnl: .unrealisedPnl, leverage: .leverage}'
    exec:
      plugin: bybit-v5
      method: account.getPositions

  get-transaction-log:
    description: Retrieves transaction logs for the unified account.
    input:
      account_type: { type: string, default: "UNIFIED", description: "Account type (UNIFIED, SPOT, CLASSIC)" }
      category: { type: string, description: "Product category (spot, linear, inverse, option)" }
      type: { type: string, description: "Transaction type (DEPOSIT, WITHDRAW, TRANSFER, etc.)" }
      coin: { type: string, description: "Coin to filter by (optional)" }
      limit: { type: integer, default: 20, description: "Limit for data size, max 50" }
    output:
      type: json
    transform:
      - jq: '.result.list[] | {timestamp: (.createdTime | tonumber | strftime("%Y-%m-%d %H:%M:%S")), type: .type, coin: .coin, amount: .amount, category: .category}'
    exec:
      plugin: bybit-v5
      method: account.getTransactionLog

  get-borrow-history:
    description: Retrieves borrow history for margin trading.
    input:
      category: { type: string, default: "spot", description: "Product category (spot)" }
      coin: { type: string, description: "Coin to filter by (optional)" }
      limit: { type: integer, default: 20, description: "Limit for data size, max 50" }
    output:
      type: json
    transform:
      - jq: '.result.list[] | {timestamp: (.createdTime | tonumber | strftime("%Y-%m-%d %H:%M:%S")), coin: .coin, borrowAmount: .borrowAmount, interestRate: .interestRate, loanStatus: .loanStatus}'
    exec:
      plugin: bybit-v5
      method: account.getBorrowHistory

  # --- Trading Pipes (10) ---

  place-order:
    description: Places a new order (limit, market, etc.).
    input:
      category: { type: string, required: true, description: "Product category (spot, linear, inverse, option)" }
      symbol: { type: string, required: true, description: "Trading pair, e.g., BTCUSDT" }
      side: { type: string, required: true, description: "Order side (Buy, Sell)" }
      order_type: { type: string, required: true, description: "Order type (Limit, Market, TakeProfit, StopLoss, TrailingStop)" }
      qty: { type: number, required: true, description: "Order quantity" }
      price: { type: number, description: "Order price (required for Limit orders)" }
      time_in_force: { type: string, default: "GTC", description: "Time in force (GTC, IOC, FOK, PostOnly)" }
      reduce_only: { type: boolean, default: false, description: "True to reduce position, False otherwise" }
      close_on_trigger: { type: boolean, default: false, description: "True to close position when trigger price is reached (for conditional orders)" }
      is_leverage: { type: integer, description: "Whether to use leverage for spot margin trading (0 for no, 1 for yes)" }
      trigger_price: { type: number, description: "Trigger price for conditional orders (StopLoss, TakeProfit, TrailingStop)" }
      tpsl_mode: { type: string, description: "TP/SL mode for linear/inverse (Full, Partial)" }
    output:
      type: json
    transform:
      - jq: '{orderId: .result.orderId, orderLinkId: .result.orderLinkId}'
    exec:
      plugin: bybit-v5
      method: trade.placeOrder

  cancel-order:
    description: Cancels an active order by ID or link ID.
    input:
      category: { type: string, required: true, description: "Product category (spot, linear, inverse, option)" }
      symbol: { type: string, required: true, description: "Trading pair, e.g., BTCUSDT" }
      order_id: { type: string, description: "Order ID (optional, use order_link_id if not provided)" }
      order_link_id: { type: string, description: "Custom order link ID (optional)" }
    output:
      type: json
    transform:
      - jq: '{orderId: .result.orderId, orderLinkId: .result.orderLinkId, status: "Cancelled"}'
    exec:
      plugin: bybit-v5
      method: trade.cancelOrder

  cancel-all-orders:
    description: Cancels all active orders for a symbol or category.
    input:
      category: { type: string, required: true, description: "Product category (spot, linear, inverse, option)" }
      symbol: { type: string, description: "Trading pair, e.g., BTCUSDT (optional, cancels all in category if omitted)" }
    output:
      type: json
    transform:
      - jq: '.result | {success: true, cancelledOrders: .list}'
    exec:
      plugin: bybit-v5
      method: trade.cancelAllOrders

  get-open-orders:
    description: Retrieves active (open) orders.
    input:
      category: { type: string, required: true, description: "Product category (spot, linear, inverse, option)" }
      symbol: { type: string, description: "Trading pair, e.g., BTCUSDT (optional)" }
      limit: { type: integer, default: 20, description: "Limit for data size, max 50" }
    output:
      type: json
    transform:
      - jq: '.result.list[] | {symbol: .symbol, orderId: .orderId, side: .side, orderType: .orderType, qty: .qty, price: .price, status: .orderStatus, createdTime: (.createdTime | tonumber | strftime("%Y-%m-%d %H:%M:%S"))}'
    exec:
      plugin: bybit-v5
      method: trade.getOpenOrders

  get-order-history:
    description: Retrieves historical orders (filled, cancelled, etc.).
    input:
      category: { type: string, required: true, description: "Product category (spot, linear, inverse, option)" }
      symbol: { type: string, description: "Trading pair, e.g., BTCUSDT (optional)" }
      limit: { type: integer, default: 20, description: "Limit for data size, max 50" }
      start_time: { type: integer, description: "Start time in milliseconds (optional)" }
      end_time: { type: integer, description: "End time in milliseconds (optional)" }
    output:
      type: json
    transform:
      - jq: '.result.list[] | {symbol: .symbol, orderId: .orderId, side: .side, orderType: .orderType, qty: .qty, price: .price, status: .orderStatus, createdTime: (.createdTime | tonumber | strftime("%Y-%m-%d %H:%M:%S"))}'
    exec:
      plugin: bybit-v5
      method: trade.getOrderHistory

  get-trade-history:
    description: Retrieves personal trade history.
    input:
      category: { type: string, required: true, description: "Product category (spot, linear, inverse, option)" }
      symbol: { type: string, description: "Trading pair, e.g., BTCUSDT (optional)" }
      limit: { type: integer, default: 20, description: "Limit for data size, max 50" }
      start_time: { type: integer, description: "Start time in milliseconds (optional)" }
      end_time: { type: integer, description: "End time in milliseconds (optional)" }
    output:
      type: json
    transform:
      - jq: '.result.list[] | {symbol: .symbol, orderId: .orderId, tradeId: .execId, side: .side, price: .execPrice, qty: .execQty, fee: .execFee, tradeTime: (.execTime | tonumber | strftime("%Y-%m-%d %H:%M:%S"))}'
    exec:
      plugin: bybit-v5
      method: trade.getTradeHistory

  set-leverage:
    description: Sets the leverage for a derivatives symbol.
    input:
      category: { type: string, required: true, description: "Product category (linear, inverse)" }
      symbol: { type: string, required: true, description: "Trading pair, e.g., BTCUSDT" }
      buy_leverage: { type: number, required: true, description: "Leverage for long positions" }
      sell_leverage: { type: number, required: true, description: "Leverage for short positions" }
    output:
      type: json
    transform:
      - jq: '{symbol: .result.symbol, buyLeverage: .result.buyLeverage, sellLeverage: .result.sellLeverage, status: "Success"}'
    exec:
      plugin: bybit-v5
      method: position.setLeverage

  set-margin-mode:
    description: Sets the margin mode (Isolated or Cross) for a derivatives symbol.
    input:
      category: { type: string, required: true, description: "Product category (linear, inverse)" }
      symbol: { type: string, required: true, description: "Trading pair, e.g., BTCUSDT" }
      trade_mode: { type: integer, required: true, description: "Trade mode (0 for cross margin, 1 for isolated margin)" }
      buy_leverage: { type: number, description: "Leverage for long (required if isolated)" }
      sell_leverage: { type: number, description: "Leverage for short (required if isolated)" }
    output:
      type: json
    transform:
      - jq: '{symbol: .result.symbol, tradeMode: .result.tradeMode, status: "Success"}'
    exec:
      plugin: bybit-v5
      method: position.setMarginMode

  get-risk-limit:
    description: Retrieves risk limit information for a derivatives symbol.
    input:
      category: { type: string, required: true, description: "Product category (linear, inverse)" }
      symbol: { type: string, required: true, description: "Trading pair, e.g., BTCUSDT" }
    output:
      type: json
    transform:
      - jq: '.result.list[] | {symbol: .symbol, riskId: .riskId, limit: .limit, maintainMargin: .maintainMargin, initialMargin: .initialMargin}'
    exec:
      plugin: bybit-v5
      method: position.getRiskLimit

  set-dcp:
    description: Sets the delivery confirmation parameter for USDC derivatives.
    input:
      category: { type: string, required: true, description: "Product category (option, linear, inverse)" }
      dcp: { type: string, required: true, description: "Delivery Confirmation Parameter (PERMIT_DELIVERY, AUTO_DELIVERY)" }
    output:
      type: json
    transform:
      - jq: '{status: "Success"}'
    exec:
      plugin: bybit-v5
      method: account.setDCP
```

---

**How to Use:**

1.  **Save:** Save the above YAML content to a file, for example, `bybit_pipes.yaml`.
2.  **Configure Gemini-CLI:**
    *   Ensure your Bybit API keys are set up in `~/.gemini/config.yaml`:
        ```yaml
        plugins:
          bybit-v5:
            api_key: YOUR_BYBIT_API_KEY
            api_secret: YOUR_BYBIT_API_SECRET
            # Set to true for testnet
            # testnet: true
        ```
    *   Reference your `bybit_pipes.yaml` in your main `~/.gemini/config.yaml`:
        ```yaml
        pipes:
          import:
            - bybit_pipes.yaml
        ```
3.  **Run Commands:**

    ```bash
    # Get 1-hour Klines for BTCUSDT (linear)
    gemini get-kline BTCUSDT 60 --category linear

    # Get ticker for BTCUSDT (spot)
    gemini get-ticker --category spot --symbol BTCUSDT

    # Get orderbook for ETHUSDT (linear)
    gemini get-orderbook --category linear --symbol ETHUSDT

    # Get your unified account balance
    gemini get-wallet-balance --account_type UNIFIED

    # Get your open positions on linear contracts
    gemini get-positions --category linear

    # Place a limit buy order for 0.001 BTC at 30000 USDT on linear
    gemini place-order --category linear --symbol BTCUSDT --side Buy --order_type Limit --qty 0.001 --price 30000

    # Cancel a specific order (replace with your order ID)
    gemini cancel-order --category linear --symbol BTCUSDT --order_id YOUR_ORDER_ID

    # Get your open orders on spot
    gemini get-open-orders --category spot

    # Set leverage to 10x for BTCUSDT (linear)
    gemini set-leverage --category linear --symbol BTCUSDT --buy_leverage 10 --sell_leverage 10
    ```

These pipes provide a solid foundation for interacting with the Bybit V5 API via Gemini-CLI, offering a convenient way to automate and query your trading activities.
%
