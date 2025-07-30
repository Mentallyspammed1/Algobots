```markdown
# Pyrmethus's Ultra Scalper Bot (PSG)

## Project Overview

Pyrmethus's Ultra Scalper Bot (PSG) is an advanced, asynchronous cryptocurrency trading bot designed for scalping strategies on the Bybit exchange. It leverages technical indicators, real-time market data, and robust position management via Bybit's WebSocket API to automate trading decisions. The bot is built with a modular architecture, allowing for easy customization of trading strategies, indicators, and risk parameters.

**Key Features:**

*   **Automated Scalping:** Executes rapid buy and sell trades based on defined technical signals.
*   **Bybit Integration:** Seamlessly connects to Bybit's REST and WebSocket APIs for order execution, data fetching, and real-time position updates.
*   **Asynchronous Operations:** Built with `asyncio` for efficient handling of concurrent network requests and market data processing.
*   **Technical Indicators:** Incorporates Stochastic RSI and Fibonacci Pivot Points for signal generation and market analysis.
*   **Dynamic Position Management:** Utilizes WebSocket updates as the single source of truth for the bot's open position, ensuring high accuracy and responsiveness.
*   **Configurable Strategy:** All critical trading parameters, indicator settings, and risk management (Stop Loss, Take Profit) are externalized in `config.py`.
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
    *   **Data Processing:** Transforms raw kline data into a Pandas DataFrame.
    *   **Indicator Calculation:** Calculates Stochastic RSI (`stoch_k`, `stoch_d`) and Fibonacci Pivot Points (resistance, support levels) based on the latest kline data.
    *   **Market Information Display:** Prints current price, indicator values, and detected support/resistance levels to the console for user visibility.
    *   **Signal Generation:**
        *   If no position is open: `strategy.py` is called to generate potential `BUY` or `SELL` entry signals based on the configured StochRSI conditions and optionally pivot points.
        *   If a position is open: `strategy.py` is called to generate potential `EXIT` signals (e.g., StochRSI reversal for the current position side).
    *   **Trade Execution:**
        *   **Entry:** If an entry signal is detected and no position is open, the bot calculates the order quantity (based on `USDT_AMOUNT_PER_TRADE`) and attempts to place a Market order with optional Stop Loss and Take Profit levels on Bybit.
        *   **Exit:** If an exit signal is detected and a position is open, the bot attempts to place a Market order to close the current position.
    *   **Position State Update:** Crucially, after any trade execution (or independently), the `_handle_position_update` callback, triggered by the WebSocket, is responsible for updating `self.position_open`, `self.current_position_side`, `self.current_position_size`, and `self.current_entry_price`. This ensures the bot's internal state accurately reflects the exchange. When a position closes, `trade_metrics` are updated.
    *   **Polling Interval:** The bot pauses for a configurable `POLLING_INTERVAL_SECONDS` before the next iteration.

## Core Trading Logic

The bot's trading decisions are primarily driven by two technical indicators:

1.  **Stochastic RSI (StochRSI):**
    *   Calculated using `indicators.py`.
    *   **Entry Signals:**
        *   **Buy:** Typically generated when StochRSI `K` and `D` lines are below `STOCHRSI_OVERSOLD_LEVEL` and either `K` crosses above `D` (if `USE_STOCHRSI_CROSSOVER` is True) or both are simply oversold and potentially turning up.
        *   **Sell:** Typically generated when StochRSI `K` and `D` lines are above `STOCHRSI_OVERBOUGHT_LEVEL` and either `K` crosses below `D` (if `USE_STOCHRSI_CROSSOVER` is True) or both are simply overbought and potentially turning down.
    *   **Exit Signals:**
        *   **Close Buy (Sell Signal):** When the StochRSI for an active `BUY` position moves into overbought territory and potentially shows a bearish reversal.
        *   **Close Sell (Buy Signal):** When the StochRSI for an active `SELL` position moves into oversold territory and potentially shows a bullish reversal.

2.  **Fibonacci Pivot Points:**
    *   Calculated using `indicators.py`.
    *   These provide dynamic support and resistance levels based on recent price action. While not directly used for signal *generation* in the provided `strategy.py` (which focuses on StochRSI), they are calculated and displayed, offering valuable contextual information for manual analysis or potential future strategy enhancements.

### Risk Management

*   **Fixed USDT Amount:** `USDT_AMOUNT_PER_TRADE` defines the capital allocated per trade, allowing the bot to dynamically calculate the quantity based on the current market price and instrument's minimum quantity requirements.
*   **Stop Loss (SL):** Configurable via `STOP_LOSS_PCT`. If set, a market stop loss order is attached to the entry trade, automatically closing the position if the price moves unfavorably by a specified percentage.
*   **Take Profit (TP):** Configurable via `TAKE_PROFIT_PCT`. If set, a market take profit order is attached to the entry trade, automatically closing the position if the price moves favorably by a specified percentage.

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
*   **`indicators.py`**: A module dedicated to calculating various technical indicators (e.g., Stochastic RSI, Fibonacci Pivot Points) based on OHLCV data.
*   **`strategy.py`**: Encapsulates the core trading logic. It defines the rules for generating `BUY`, `SELL`, and `EXIT` signals based on the calculated indicators and market conditions.
*   **`bybit_api.py`**: An asynchronous client for interacting with the Bybit REST and WebSocket APIs. It handles API authentication, request retries, and parsing responses.
*   **`bot_logger.py`**: Configures and provides a custom logging setup for the bot, ensuring clear and informative output, often with color-coding for readability.
*   **`trade_metrics.py`**: Manages the tracking and calculation of trade performance metrics such as total PnL, win rate, total trades, and average PnL per trade.
*   **`utils.py`**: A collection of utility functions that support the bot's operations, such as calculating order quantities based on USDT amount and exchange lot size filters.
*   **`color_codex.py`**: Defines ANSI escape codes for colored console output, enhancing the readability of bot logs.

## Setup and Installation

### Prerequisites

*   Python 3.9+
*   `pip` (Python package installer)

### Bybit API Keys

You need Bybit API keys with appropriate permissions (Trade, Read). **It is highly recommended to use environment variables for your API keys for security.**

1.  **Create a `.env` file** in the root directory of the project (same location as `PSG.py`).
2.  **Add your API keys** to this file:
    ```
    BYBIT_API_KEY=YOUR_BYBIT_API_KEY
    BYBIT_API_SECRET=YOUR_BYBIT_API_SECRET
    ```
    (Note: The current `PSG.py` uses `os.getenv` directly, implying `python-dotenv` might be needed if you prefer `.env` files over setting system-wide environment variables.)

### Installation Steps

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd pyrmethus-bot # Or whatever your project folder is named
    ```
2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: `venv\Scripts\activate`
    ```
3.  **Install dependencies:**
    The bot relies on several libraries. Create a `requirements.txt` file with the following content:
    ```
    pandas
    aiohttp  # Required by bybit_api.py for async HTTP requests
    python-dotenv # If using .env file for API keys
    ```
    Then install them:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration (`config.py`)

The `config.py` file allows you to customize the bot's behavior. Here are the key parameters:

```python
# --- Trading Pair and Interval ---
SYMBOL = "BTCUSDT"  # Trading pair (e.g., BTCUSDT, ETHUSDT)
INTERVAL = "15"     # Candlestick interval (e.g., "1", "5", "15", "60", "D")
USDT_AMOUNT_PER_TRADE = 10.0 # Amount of USDT to use for each trade (e.g., 10.0 for $10 worth)

# --- Fibonacci Pivot Point Settings ---
PIVOT_LEFT_BARS = 2  # Number of bars to the left to confirm a pivot
PIVOT_RIGHT_BARS = 2 # Number of bars to the right to confirm a pivot
PIVOT_TOLERANCE_PCT = 0.0005 # Percentage tolerance for pivot point detection

# --- Stochastic RSI Settings ---
STOCHRSI_K_PERIOD = 14 # K period for StochRSI
STOCHRSI_D_PERIOD = 3  # D period for StochRSI
STOCHRSI_OVERBOUGHT_LEVEL = 80 # StochRSI level considered overbought
STOCHRSI_OVERSOLD_LEVEL = 20  # StochRSI level considered oversold
USE_STOCHRSI_CROSSOVER = True # If True, requires K/D crossover for signals

# --- Risk Management ---
STOP_LOSS_PCT = 0.005 # Percentage stop loss (e.g., 0.005 for 0.5%)
TAKE_PROFIT_PCT = 0.01 # Percentage take profit (e.g., 0.01 for 1%)

# --- Bybit API Settings ---
BYBIT_API_ENDPOINT = "https://api.bybit.com" # Or "https://api-testnet.bybit.com" for testnet
BYBIT_CATEGORY = "linear" # Trading category: "linear" (USDT perpetual), "inverse", "spot", "option"

# --- Bot Operation Settings ---
CANDLE_FETCH_LIMIT = 200 # Number of historical candles to fetch for analysis
POLLING_INTERVAL_SECONDS = 10 # How often the bot checks for new signals (in seconds)
API_REQUEST_RETRIES = 3 # Number of retries for failed API requests
API_BACKOFF_FACTOR = 0.5 # Factor for exponential backoff between retries
```

**Before running, ensure these parameters are set according to your trading preferences and risk tolerance.**

## Usage

Once configured and dependencies are installed:

1.  **Ensure your API keys are set as environment variables** or in a `.env` file.
2.  **Run the bot:**
    ```bash
    python PSG.py
    ```

The bot will start logging its operations, market data, and trade decisions to the console.

## Logging and Output

The bot provides detailed and color-coded logs to the console, making it easy to monitor its activity:

*   **Informational messages:** General updates, state changes.
*   **Success messages:** Position opened/closed, trade executed.
*   **Warning messages:** Insufficient data, minor issues.
*   **Error messages:** Critical issues, API failures.
*   **Market Information:** Displays current price, StochRSI values, and detected support/resistance levels.
*   **Trade Metrics:** Periodically logs overall trade statistics (total PnL, win rate, etc.) after a trade is closed.

Example output snippets:

*   `[INFO] 🎉 Position detected and tracked via WebSocket for BTCUSDT.`
*   `[INFO] 💼 Open Position (WS): Buy 0.0010 BTCUSDT at 30000.00. Unrealized PnL: 0.0123`
*   `[INFO] 💡 Detected BUY signal at 29950.00 (Info: StochRSI Crossover)`
*   `[INFO] 📈 StochRSI K: 25.45, D: 21.80`
*   `[INFO] Resistance Levels Detected:`
    `  - 30100.00 (R1)`
*   `[INFO] Overall Trade Statistics: Total PnL: $5.23, Win Rate: 60.00% (3/5)`

## Important Considerations and Disclaimer

*   **Trading Risks:** Automated trading carries significant financial risks. Past performance is not indicative of future results. **Only trade with capital you can afford to lose.**
*   **Testnet First:** Always test the bot thoroughly on the Bybit Testnet (`BYBIT_API_ENDPOINT = "https://api-testnet.bybit.com"`) with testnet API keys before deploying to a live account.
*   **Customization:** The provided `strategy.py` is a basic example. Users are encouraged to modify `strategy.py` and `indicators.py` to implement their own sophisticated trading logic and indicator combinations.
*   **API Rate Limits:** The bot includes basic retry and backoff mechanisms for API requests, but be mindful of Bybit's rate limits. Excessive requests can lead to temporary bans.
*   **Connectivity:** Ensure a stable internet connection for continuous operation.
*   **Monitoring:** Even with automation, continuous monitoring of the bot's performance and market conditions is highly recommended.

This detailed documentation should provide a comprehensive understanding of Pyrmethus's Ultra Scalper Bot, its functionality, and how to set it up and run it.
```
