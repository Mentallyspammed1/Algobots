```markdown
# Pyrmethus's Ultra Scalper Bot (PSG) - Transmuted

## Project Overview

Pyrmethus's Ultra Scalper Bot (PSG) is an advanced, asynchronous cryptocurrency trading bot designed for scalping strategies on the Bybit exchange. It has been significantly enhanced to incorporate market-making principles, high-precision mathematics, and a more resilient architecture. It leverages technical indicators, real-time market data, and robust position management via Bybit's WebSocket API to automate trading decisions. The bot is built with a modular architecture, allowing for easy customization of trading strategies, indicators, and risk parameters.

**Key Features:**

*   **Automated Scalping:** Executes rapid buy and sell trades based on defined technical signals.
*   **Bybit Integration:** Seamlessly connects to Bybit's REST and WebSocket APIs for order execution, data fetching, and real-time position updates.
*   **Asynchronous Operations:** Built with `asyncio` for efficient handling of concurrent network requests and market data processing.
*   **High-Precision Calculations:** Utilizes Python's `Decimal` type for all price and quantity calculations, eliminating floating-point inaccuracies.
*   **Advanced Technical Indicators:** Incorporates Stochastic RSI, Fibonacci Pivot Points, and Average True Range (ATR) for a more nuanced market analysis.
*   **Dynamic Position Management:** Utilizes WebSocket updates as the single source of truth for the bot's open position, ensuring high accuracy and responsiveness.
*   **Dynamic Risk Management:** Automatically sets and adjusts Take Profit and Stop Loss orders for open positions via `set_trading_stop`, reacting in real-time to market changes.
*   **Configurable Strategy:** All critical trading parameters, indicator settings, and risk management are externalized in `config.py`.
*   **Comprehensive Logging & Trade Metrics:** Provides detailed, color-coded console output and logs, along with real-time trade performance tracking (PnL, win rate, etc.).
*   **Modular Design:** Separates concerns into distinct Python modules for clarity, maintainability, and extensibility.
*   **Robust Error Handling:** Includes mechanisms for API request retries, backoff, and graceful recovery from common issues.

## Architecture and Workflow

The `PyrmethusBot` class is the central orchestrator of the trading system. Its core loop operates as follows:

1.  **Initialization:**
    *   Sets up logging and trade metrics.
    *   Initializes the `BybitContractAPI` client.
    *   Starts a WebSocket listener in a background task to receive real-time position updates from Bybit. This is crucial for maintaining an accurate internal state of open positions.
    *   Performs an initial REST API call to check for any existing open positions, handling cases where the bot restarts or WebSocket updates are delayed.

2.  **Main Trading Loop (`run` method):**
    *   **Data Fetching:** Periodically fetches historical kline (candlestick) data from Bybit using the REST API.
    *   **Data Processing:** Transforms raw kline data into a Pandas DataFrame, using `Decimal` for precision.
    *   **Indicator Calculation:** Calculates Stochastic RSI (`stoch_k`, `stoch_d`), Fibonacci Pivot Points (resistance, support levels), and ATR based on the latest kline data.
    *   **Market Information Display:** Prints current price, indicator values, and detected support/resistance levels to the console for user visibility.
    *   **Signal Generation:**
        *   If no position is open: `strategy.py` is called to generate potential `BUY` or `SELL` entry signals based on the configured StochRSI conditions and optionally pivot points.
        *   If a position is open: `strategy.py` is called to generate potential `EXIT` signals (e.g., StochRSI reversal for the current position side).
    *   **Trade Execution:**
        *   **Entry:** If an entry signal is detected and no position is open, the bot calculates the order quantity (based on `USDT_AMOUNT_PER_TRADE`) and attempts to place a Market order.
        *   **Exit:** If an exit signal is detected and a position is open, the bot attempts to place a Market order to close the current position.
    *   **Position State Update:** Crucially, after any trade execution (or independently), the `_handle_position_update` callback, triggered by the WebSocket, is responsible for updating the bot's internal state. When a position is opened or its size changes, the bot automatically calls `_update_take_profit_stop_loss` to set or adjust the TP/SL on the exchange.
    *   **Polling Interval:** The bot pauses for a configurable `POLLING_INTERVAL_SECONDS` before the next iteration.

## Core Trading Logic

The bot's trading decisions are primarily driven by three technical indicators:

1.  **Stochastic RSI (StochRSI):**
    *   Calculated using `indicators.py`.
    *   Used to identify overbought and oversold conditions, as well as momentum shifts.

2.  **Fibonacci Pivot Points:**
    *   Calculated using `indicators.py`.
    *   These provide dynamic support and resistance levels based on recent price action.

3.  **Average True Range (ATR):**
    *   Calculated using `indicators.py`.
    *   Provides a measure of market volatility, which can be used to adjust trade sizing or other risk parameters in future enhancements.

### Risk Management

*   **Fixed USDT Amount:** `USDT_AMOUNT_PER_TRADE` defines the capital allocated per trade, allowing the bot to dynamically calculate the quantity based on the current market price and instrument's minimum quantity requirements.
*   **Dynamic Stop Loss (SL) and Take Profit (TP):** Configurable via `STOP_LOSS_PCT` and `TAKE_PROFIT_PCT`. The bot now uses the `set_trading_stop` API endpoint to manage these for any open position, ensuring they are always active and correctly calculated based on the position's entry price.

## Project Structure

```
.
├── PSG.py
├── config.py
├── indicators.py
├── strategy.py
├── bybit_api.py
├── bot_logger.py
├── trade_metrics.py
├── utils.py
└── color_codex.py
```

*   **`PSG.py`**: The main execution file. Contains the `PyrmethusBot` class, orchestrating the entire trading logic, API interactions, and state management.
*   **`config.py`**: Stores all configurable parameters for the bot, including API endpoints, trading symbols, intervals, indicator settings, risk parameters, and logging levels.
*   **`indicators.py`**: A module dedicated to calculating various technical indicators (e.g., Stochastic RSI, Fibonacci Pivot Points, ATR) based on OHLCV data, now using `Decimal` for high precision.
*   **`strategy.py`**: Encapsulates the core trading logic. It defines the rules for generating `BUY`, `SELL`, and `EXIT` signals based on the calculated indicators and market conditions.
*   **`bybit_api.py`**: An asynchronous client for interacting with the Bybit REST and WebSocket APIs. It handles API authentication, request retries, and parsing responses. It now includes the `set_trading_stop` method for dynamic risk management.
*   **`bot_logger.py`**: Configures and provides a custom logging setup for the bot, ensuring clear and informative output, often with color-coding for readability.
*   **`trade_metrics.py`**: Manages the tracking and calculation of trade performance metrics such as total PnL, win rate, total trades, and average PnL per trade.
*   **`utils.py`**: A collection of utility functions that support the bot's operations, such as calculating order quantities based on USDT amount and exchange lot size filters.
*   **`color_codex.py`**: Defines ANSI escape codes for colored console output, enhancing the readability of bot logs.

## Recent Enhancements (July 2025)

*   **High-Precision Calculations:** The bot now uses Python's `Decimal` type for all price and quantity calculations, preventing common floating-point inaccuracies.
*   **Dynamic Risk Management:** The bot now uses the `set_trading_stop` API endpoint to manage Take Profit and Stop Loss orders for open positions, ensuring they are always active and correctly calculated.
*   **ATR Indicator:** The bot now calculates the Average True Range (ATR) to measure market volatility.
*   **Robust Authentication:** The Bybit API client has been significantly improved to handle both REST and WebSocket authentication more reliably, with enhanced error handling and logging.

## Setup and Installation

(Setup and installation instructions remain the same as in the `README.md`)

## Important Considerations and Disclaimer

(Disclaimer remains the same as in the `README.md`)
```