The `pyrm_ultimate.py` script has been significantly enhanced and upgraded, incorporating the "45 mystical insights for supreme trading mastery" and beyond.

Here's a summary of the key improvements and new features:

**Core Infrastructure & Robustness:**

1.  **Enhanced Logging (Insight #1):** Improved `setup_logging` with `RotatingFileHandler` for log rotation and `ColoredFormatter` for better console readability.
2.  **Environment Variable Loading (Insight #2):** Confirmed `load_dotenv(override=True)` for immediate configuration updates.
3.  **Decimal Precision & Rounding (Insight #3):** Global `Decimal` precision and `ROUND_DOWN` rounding are enforced for all financial calculations.
4.  **Custom Exceptions (Insight #16):** `TradingBotError`, `InsufficientBalanceError`, `OrderPlacementError`, `MaxDrawdownExceeded`, and `RateLimitExceeded` are defined and used for clearer error handling.
5.  **Enhanced Circuit Breaker (Insight #18):** `EnhancedCircuitBreaker` now includes `half_open_success_threshold` for gradual recovery and tracks `failure_reasons`. It's integrated into `_http_call`.
6.  **Database Manager (Insight #31):** `DatabaseManager` is fully implemented using `sqlite3` for persistent storage of:
    *   Orders (`orders` table).
    *   Trade executions (`trades` table).
    *   Performance snapshots (`performance_snapshots` table).
    *   Market regime history (`market_regime` table).
    *   It uses a `threading.Lock` for thread-safe access.
7.  **Asynchronous HTTP Calls with Thread Pool (Insight #32):** `_http_call` now uses `asyncio.to_thread` to make blocking `pybit` HTTP calls non-blocking, improving overall responsiveness. `ThreadPoolExecutor` is explicitly used.
8.  **Secure API Key Management (Insight #34):** `SecureConfig` class uses `cryptography.fernet` to encrypt/decrypt API keys. The bot now attempts to load encrypted keys from `.env` (e.g., `BYBIT_API_KEY_ENC`) and decrypts them. If no encrypted key is found, it falls back to plain text.
9.  **Rate Limiter (Insight #40):** A sophisticated `RateLimiter` class tracks calls per endpoint and enforces Bybit's API rate limits with dynamic waiting. It's fully integrated into `_http_call`.
10. **Graceful Shutdown:** Implemented `shutdown()` method to handle `SIGINT` and `SIGTERM` signals, ensuring all open orders are cancelled, WebSocket connections are closed, and the database is properly shut down before exiting.

**Market Data & Analytics:**

11. **Market Regime Enumeration (Insight #35):** `MarketRegime` Enum is defined for clear state representation.
12. **Enhanced Performance Metrics (Insight #38):** `EnhancedPerformanceMetrics` dataclass now tracks:
    *   `total_fills`, `total_market_closes`.
    *   `winning_trades`, `losing_trades`.
    *   `max_drawdown` (as a percentage).
    *   `peak_equity` and `current_equity`.
    *   `_equity_history` for ratio calculations.
    *   `_trade_returns` for individual trade PnLs.
    *   `fill_rates` and `slippage_stats`.
    *   Includes methods for `get_win_rate`, `get_profit_factor` (conceptual), `update_drawdown`, `record_equity_snapshot`, `record_trade_pnl`, `update_fill_rate`, `record_slippage`.
13. **Sharpe Ratio Calculation (Insight #39):** `calculate_sharpe_ratio` is implemented in `EnhancedPerformanceMetrics` using `numpy`.
14. **Sortino Ratio Calculation:** `calculate_sortino_ratio` is added, focusing on downside deviation.
15. **Calmar Ratio Calculation:** `calculate_calmar_ratio` is added (simplified for demonstration).
16. **Market Microstructure Analyzer (Insight #41):** `MarketMicrostructureAnalyzer` tracks and provides insights on:
    *   `order_flow_imbalance` (updated from orderbook).
    *   `spread_history` (updated from orderbook).
    *   `volume_profile` (updated from public trade streams).
    *   `get_order_flow_signal` and `get_average_spread` methods.
    *   `detect_market_regime` uses `numpy` for more robust trend and volatility analysis, returning a `MarketRegime` and confidence score.
17. **WebSocket Message Sequencing (Insight #44):** `_message_sequence` is used in `handle_orderbook` to filter out stale or out-of-order WebSocket messages.
18. **Custom WebSocket Ping Interval (Insight #45):** Configured `ping_interval` and `ping_timeout` for better WebSocket health management.
19. **Public Trade Stream Handling:** `_handle_public_trade` is added to process trade data from public WebSocket, which can be used for volume profile analysis.

**Order Management & Trading Logic:**

20. **Smart Order Manager (Insight #42):** `SmartOrderManager` is enhanced to support:
    *   `add_order_layer`: To track relationships between a base order and its layered components.
    *   `add_iceberg_order`: To track parameters of iceberg orders.
    *   `update_iceberg_fill`: To manage the filled quantity of iceberg orders and determine the next visible part (conceptual, requires external replenishment logic).
    *   `get_active_iceberg_orders`: To retrieve active iceberg orders.
21. **Order Layering (`place_order_with_layers`):** A new method allows placing a single logical order as multiple smaller limit orders spread across price levels, improving fill rates and reducing market impact.
22. **Iceberg Order Framework (`place_iceberg_order`, `manage_iceberg_orders`):** A framework for client-side iceberg order management is introduced. While `manage_iceberg_orders` is a conceptual placeholder (as Bybit doesn't natively auto-replenish client-side icebergs), the `SmartOrderManager` can track them.
23. **Advanced Position Sizing (`calculate_position_size`):**
    *   Integrates `MaxDrawdownExceeded` check, raising an exception if limits are breached.
    *   Includes a simplified, cautious Kelly Criterion-like adjustment based on win rate to dynamically size positions.
    *   Validates against `minOrderQty` and `min_notional_usd`.
24. **Comprehensive Order Placement (`place_order`):** Centralized order placement with `dry_run` support, metric updates, and robust error handling.
25. **Efficient Order Cancellation (`cancel_all_tracked_orders`):** Iterates through tracked orders to cancel them, improving cleanup.

**Monitoring & Alerts:**

26. **Termux Toast Notifications (`_async_termux_toast`):** Added functionality to send push notifications via Termux (for Android users) for critical alerts like max drawdown.
27. **Detailed Performance Logging:** The main loop now logs more comprehensive performance metrics (equity, P&L, drawdown, win rate) at regular intervals.

**Example Strategy (Insight #46 - New Insight):**

*   A `simple_momentum_strategy` function is provided as an example. It demonstrates how to use the bot's new features:
    *   Retrieves market data and current position.
    *   Utilizes `MarketMicrostructureAnalyzer` to detect `MarketRegime` and `order_flow_signal`.
    *   Closes positions if the market regime becomes uncertain.
    *   Opens new positions (using `place_order_with_layers`) based on strong trending regimes and positive order flow, with position sizing determined by `calculate_position_size`.
    *   Crucially, it handles the `MaxDrawdownExceeded` exception, stopping trading if the limit is hit.

This upgraded version transforms the bot into a more robust, feature-rich, and intelligent trading system, laying a strong foundation for advanced algorithmic strategies.

To run this enhanced bot:

1.  **Install Dependencies:**
    ```bash
    pip install python-dotenv pybit-unified-trading colorama numpy cryptography
    ```
2.  **Configure `.env`:**
    ```
    BYBIT_API_KEY=YOUR_LIVE_API_KEY
    BYBIT_API_SECRET=YOUR_LIVE_API_SECRET
    # OR, for encrypted keys (generate ENCRYPTION_KEY first, then encrypt your API_KEY and API_SECRET)
    # ENCRYPTION_KEY=your_generated_fernet_key_here
    # BYBIT_API_KEY_ENC=gAAAAAB...
    # BYBIT_API_SECRET_ENC=gAAAAAB...

    BYBIT_USE_TESTNET=False # Set to True for testnet
    BYBIT_LOG_LEVEL=INFO # DEBUG, INFO, WARNING, ERROR, CRITICAL

    BOT_MAX_OPEN_POSITIONS=5
    BOT_MAX_DRAWDOWN_PCT=0.20 # 20% drawdown limit
    BOT_MIN_NOTIONAL_USD=10 # Minimum trade size in USD
    BOT_API_TIMEOUT_S=15
    BOT_ACCOUNT_REFRESH_INTERVAL_S=300
    BOT_PERFORMANCE_SNAPSHOT_INTERVAL_S=300
    DEFAULT_VOLUME_PROFILE_TICK_SIZE=0.01 # For microstructure analysis
    BOT_DEFAULT_CAPITAL_ALLOCATION_LOW_WINRATE=0.01 # For position sizing
    ```
    *To generate an `ENCRYPTION_KEY` and encrypt your API keys, you can run a small Python script:*
    ```python
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    print(f"ENCRYPTION_KEY={key.decode()}")
    f = Fernet(key)
    api_key = "YOUR_ACTUAL_API_KEY"
    api_secret = "YOUR_ACTUAL_API_SECRET"
    print(f"BYBIT_API_KEY_ENC={f.encrypt(api_key.encode()).decode()}")
    print(f"BYBIT_API_SECRET_ENC={f.encrypt(api_secret.encode()).decode()}")
    ```
    Then copy the output into your `.env` file.

3.  **Run the Bot:**
    ```bash
    python pyrm_ultimate.py --symbols BTCUSDT,ETHUSDT --interval 5
    ```
    For a dry run (no actual trades):
    ```bash
    python pyrm_ultimate.py --dry-run --symbols BTCUSDT,ETHUSDT --interval 5
    ```
