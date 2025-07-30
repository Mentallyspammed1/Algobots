# Pyrmethus's Ultra Scalper Bot (PSG) - Awakened

## 🚀 Overview

Pyrmethus's Ultra Scalper Bot (PSG) is an advanced, real-time cryptocurrency trading bot designed for high-frequency scalping on the Bybit exchange. Built with `asyncio` for concurrent operations and `pandas` for efficient data handling, PSG integrates multiple technical indicators and sophisticated position management to identify and execute rapid trade opportunities.

The bot leverages a combination of Stochastic RSI for momentum, Fibonacci Pivot Points for dynamic support/resistance, and an initial framework for Order Block identification to make precise entry and exit decisions. It also features dynamic Take Profit (TP) and Stop Loss (SL) based on Average True Range (ATR) or fixed percentages, ensuring robust risk management.

**Disclaimer:** Trading cryptocurrencies involves substantial risk and is not suitable for all investors. Past performance is not indicative of future results. This bot is provided for educational and informational purposes only. Use at your own risk.

## ✨ Features

*   **Real-time Data Processing:** Utilizes Bybit WebSocket APIs for live kline and position updates, ensuring immediate reaction to market changes.
*   **Multi-Indicator Strategy:**
    *   **Stochastic RSI:** Identifies overbought/oversold conditions and potential reversals, with optional crossover confirmation.
    *   **Fibonacci Pivot Points:** Calculates dynamic support and resistance levels based on a configurable higher timeframe, used for entry/exit confluence.
    *   **Order Block Identification (Initial):** Tracks potential supply/demand zones based on pivot highs/lows for future strategy integration.
    *   **ATR, SMA, Ehlers Fisher Transform, Ehlers Super Smoother:** Additional indicators for market analysis and potential future strategy enhancements.
*   **Dynamic Position Management:**
    *   **Flexible Entry/Exit:** Executes market orders for quick entries and exits based on generated signals.
    *   **Automatic TP/SL:** Sets Take Profit and Stop Loss orders based on configurable percentages or dynamic ATR multipliers.
    *   **Robust State Tracking:** Maintains accurate internal state of open positions, entry prices, and PnL, synchronized with exchange data via WebSockets.
*   **Precision & Reliability:**
    *   **Decimal Arithmetic:** Uses Python's `Decimal` type for all financial calculations to prevent floating-point inaccuracies.
    *   **Error Handling & Retries:** Implements retry mechanisms for API requests and robust exception handling for continuous operation.
*   **Comprehensive Logging:** Detailed logging of bot actions, trade executions, market data, and performance metrics for analysis and debugging.
*   **Modular Architecture:** Clean separation of concerns (API interaction, indicators, strategy, logging, UI) for easy maintenance and extensibility.
*   **Configurable Parameters:** All key trading parameters are externalized in `config.py` and `.env` for easy customization.

## 🧠 Core Concepts & Strategy Overview

PSG's trading logic is built around identifying high-probability scalping opportunities using a confluence of technical analysis techniques:

1.  **Stochastic RSI (Momentum):**
    *   The primary trigger for entries and exits.
    *   **Buy Signal:** Typically generated when Stoch %K and %D lines are in the oversold region and either cross up, or %K crosses above %D.
    *   **Sell Signal:** Generated when Stoch %K and %D lines are in the overbought region and either cross down, or %K crosses below %D.
    *   Configurable `STOCHRSI_K_PERIOD`, `STOCHRSI_D_PERIOD`, `STOCHRSI_OVERBOUGHT_LEVEL`, `STOCHRSI_OVERSOLD_LEVEL`, and `USE_STOCHRSI_CROSSOVER`.

2.  **Fibonacci Pivot Points (Dynamic Support/Resistance):**
    *   Calculated based on the High, Low, and Close of a previous candle from a *higher timeframe* (e.g., daily pivots on an hourly chart).
    *   Provides key price levels (e.g., R1, R2, R3, S1, S2, S3) that act as potential turning points.
    *   **Confluence:** Signals are strengthened when they occur near these pivot levels.
    *   **Actionable Levels:** `ENABLE_FIB_PIVOT_ACTIONS` allows the bot to consider these levels for entry confirmation (`FIB_ENTRY_CONFIRM_PERCENT`) or exit warnings (`FIB_EXIT_WARN_PERCENT`, `FIB_EXIT_ACTION`).

3.  **Order Blocks (Supply/Demand Zones - Initial Implementation):**
    *   Identified as candles that form a Pivot High or Pivot Low.
    *   **Bullish OB:** Formed by a pivot low candle, indicating potential demand below.
    *   **Bearish OB:** Formed by a pivot high candle, indicating potential supply above.
    *   The bot tracks these and marks them as `violated` if price closes beyond their boundaries. This is a foundational element for future, more advanced price action strategies.

4.  **Average True Range (ATR) for Volatility:**
    *   Used to calculate dynamic Take Profit and Stop Loss levels.
    *   Instead of fixed percentages, ATR-based TP/SL adapts to current market volatility, potentially leading to more optimal exit points.
    *   `ATR_MULTIPLIER_SL` and `ATR_MULTIPLIER_TP` in `config.py` control the sensitivity.

5.  **Position Management & Risk Control:**
    *   The bot maintains an `inventory` (signed quantity: positive for long, negative for short), `entry_price`, and `unrealized_pnl`.
    *   All position updates are primarily driven by Bybit's private WebSocket stream for real-time accuracy.
    *   `_update_take_profit_stop_loss` ensures TP/SL orders are always active and updated with the latest position data.
    *   Trades are logged, and overall trade statistics are maintained by the `TradeMetrics` class.

## ⚙️ Architecture

The Pyrmethus Bot is structured into several modular components to enhance readability, maintainability, and extensibility:

*   **`PSG.py` (Core Bot Logic):**
    *   The main class `PyrmethusBot` orchestrates the entire trading process.
    *   Manages bot state (position, inventory, PnL).
    *   Handles WebSocket data streams (`_handle_position_update`, `_handle_kline_update`).
    *   Calls external modules for indicator calculation, signal generation, and API interaction.
    *   Implements trade execution (`_execute_entry`, `_execute_exit`) and TP/SL management.
*   **`bybit_api.py`:**
    *   Encapsulates all interactions with the Bybit API (REST and WebSockets).
    *   Handles authentication, rate limits, and error retries.
    *   Provides methods for fetching klines, getting account info, placing orders, and setting trading stops.
*   **`indicators.py`:**
    *   Contains implementations for various technical indicators (StochRSI, ATR, SMA, Ehlers Fisher, Ehlers Super Smoother, Fibonacci Pivots).
    *   Includes `find_pivots` for identifying swing highs/lows and `handle_websocket_kline_data` for processing real-time kline updates into the DataFrame.
*   **`strategy.py`:**
    *   Houses the core trading logic for generating `entry` and `exit` signals.
    *   Evaluates current market conditions and indicator values based on the configured strategy parameters.
*   **`config.py`:**
    *   Stores all static configuration parameters for the bot (symbols, intervals, amounts, indicator settings, API endpoints, etc.).
*   **`bot_logger.py`:**
    *   Configures and manages the logging system, directing output to console and file, with custom formatting and color coding.
*   **`trade_metrics.py`:**
    *   Tracks and calculates performance metrics for trades (PnL, win rate, total fees, etc.).
*   **`bot_ui.py`:**
    *   Provides simple console-based market information display for real-time monitoring.
*   **`utils.py`:**
    *   Contains utility functions, such as `calculate_order_quantity` for precise quantity calculation based on exchange rules.
*   **`color_codex.py`:**
    *   Defines ANSI escape codes for colorful console output, improving readability.
*   **`.env`:**
    *   Used to securely store sensitive information like API keys and secrets.

The bot operates asynchronously using `asyncio`, allowing it to concurrently listen to WebSocket streams for market and position updates while performing calculations and making trading decisions in its main loop.

## 🚀 Setup & Installation

Follow these steps to get Pyrmethus Bot up and running.

### Prerequisites

*   **Python 3.9+** (Recommended)
*   A Bybit account (Testnet recommended for initial setup and testing).

### 1. Clone the Repository

```bash
git clone <repository_url>
cd pyrmethus-bot # Or whatever your project folder is named
```

### 2. Create a Virtual Environment

It's highly recommended to use a virtual environment to manage dependencies.

```bash
python -m venv venv
# On Windows
.\venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate
```

### 3. Install Dependencies

Install all required Python packages. You will likely need a `requirements.txt` file (not provided in the snippet, but commonly includes `pandas`, `python-dotenv`, `websockets`, `pybit`).

```bash
pip install pandas python-dotenv websockets pybit-sdk # Add other dependencies as needed
```

### 4. Configuration

#### a. Environment Variables (`.env`)

Create a file named `.env` in the root directory of your project. This file will store your sensitive API keys.

```
BYBIT_API_KEY=YOUR_BYBIT_API_KEY
BYBIT_API_SECRET=YOUR_BYBIT_API_SECRET
```

**Security Note:** Never commit your `.env` file to version control. Add `.env` to your `.gitignore` file.

#### b. Bot Configuration (`config.py`)

Create a file named `config.py` in the root directory (or ensure it exists if you cloned a full repo). This file contains all the trading parameters. Adjust these values according to your strategy and risk tolerance.

```python
# config.py

# --- Exchange Settings ---
SYMBOL = "BTCUSDT" # Trading pair
INTERVAL = "1"     # Kline interval (e.g., "1", "5", "15", "60", "D")
USDT_AMOUNT_PER_TRADE = 10.0 # USDT amount to trade per entry
BYBIT_API_ENDPOINT = "https://api-testnet.bybit.com" # Use "https://api.bybit.com" for live
BYBIT_CATEGORY = "linear" # "linear" for USDT Perpetuals, "inverse" for Inverse Perpetuals/Futures
CANDLE_FETCH_LIMIT = 200 # Number of historical candles to fetch initially
POLLING_INTERVAL_SECONDS = 5 # How often the main loop checks for signals (excluding WS updates)
API_REQUEST_RETRIES = 3
API_BACKOFF_FACTOR = 0.5

# --- Indicator Settings ---
# StochRSI
STOCHRSI_K_PERIOD = 14
STOCHRSI_D_PERIOD = 3
STOCHRSI_OVERBOUGHT_LEVEL = 80
STOCHRSI_OVERSOLD_LEVEL = 20
USE_STOCHRSI_CROSSOVER = True # True to require K/D crossover for signal, False for just level breach

# ATR (for dynamic TP/SL)
ATR_PERIOD = 14
ATR_MULTIPLIER_SL = 1.5 # Multiplier for ATR to set Stop Loss
ATR_MULTIPLIER_TP = 3.0 # Multiplier for ATR to set Take Profit

# Fixed Percentage TP/SL (Fallback if ATR multipliers are None or not used)
STOP_LOSS_PCT = 0.005 # 0.5%
TAKE_PROFIT_PCT = 0.01 # 1%

# Fibonacci Pivot Points
ENABLE_FIB_PIVOT_ACTIONS = True # Enable/Disable Fibonacci pivot point based actions
PIVOT_TIMEFRAME = "D" # Timeframe for calculating pivots (e.g., "D", "W", "M", "240" (4h))
FIB_LEVELS_TO_CALC = [0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618] # Fibonacci levels
FIB_NEAREST_COUNT = 3 # Number of nearest fib levels to consider for strategy
FIB_ENTRY_CONFIRM_PERCENT = 0.0005 # Price must be within this % of a fib level for entry confirmation
FIB_EXIT_WARN_PERCENT = 0.001 # Price must be within this % of a fib level to trigger exit warning
FIB_EXIT_ACTION = "aggressive" # "aggressive" (market exit) or "conservative" (wait for stoch exit)

# Order Block (Pivot High/Low) Settings
PIVOT_LEFT_BARS = 2 # Number of bars to the left for pivot identification
PIVOT_RIGHT_BARS = 2 # Number of bars to the right for pivot identification
PIVOT_TOLERANCE_PCT = 0.0005 # Percentage tolerance for pivot identification (e.g., 0.05%)

# SMA (Simple Moving Average)
SMA_PERIOD = 20 # Period for SMA calculation

# Ehlers Fisher Transform
EHLERS_FISHER_PERIOD = 10 # Period for Ehlers Fisher Transform

# Ehlers Super Smoother
EHLERS_SUPERSMOOTHER_PERIOD = 10 # Period for Ehlers Super Smoother
```

### 5. Ensure Supporting Files Exist

Verify that the following files are present in your project directory as imported by `PSG.py`:
*   `color_codex.py`
*   `config.py`
*   `indicators.py`
*   `strategy.py`
*   `bybit_api.py`
*   `bot_ui.py`
*   `bot_logger.py`
*   `trade_metrics.py`
*   `utils.py`

## ▶️ How to Run

Once configured, you can start the bot from your terminal:

```bash
python PSG.py
```

### Expected Output

The bot will display colorful log messages in your console, indicating its status, market data, signals, and trade executions. It will also generate log files in a `logs/` directory.

```
🚀 Pyrmethus's Ultra Scalper Bot - Awakened
==========================================

⚡ Initializing scalping engine and calibrating sensors...
[INFO] BybitContractAPI initialized.
[INFO] Subscribed to private WS topic: position
[INFO] Subscribed to public WS topic: kline.1.BTCUSDT
[INFO] Initial kline data fetched and processed. Current price: 68000.0000
[INFO] ✅ No open position for BTCUSDT (WS). Seeking new trade opportunities...
[INFO] 📊 Market Info for BTCUSDT (1m):
       Current Price: 68000.0000
       Last Close: 68000.0000
       Stoch K: 30.50, Stoch D: 25.00
       ATR: 50.0000
       Nearest Support: S1 (67900.0000)
       Nearest Resistance: R1 (68100.0000)
       Active Bull OBs: 1, Active Bear OBs: 0
[INFO] 💡 Detected BUY signal at 68000.0000 (Info: oversold_crossover)
[INFO] Attempting to place BUY order for 0.0010 BTCUSDT at market price...
[INFO] 🎉 Position detected and tracked via WebSocket for BTCUSDT.
[INFO] 💼 Open Position (WS): Buy 0.0010 BTCUSDT at 68000.0000. Unrealized PnL: -0.0500
[INFO] Dynamic TP/SL (ATR-based) for BTCUSDT: TP=68150.0000, SL=67925.0000
[INFO] Sleeping for 5 seconds...
...
```

## 📊 Logging & Monitoring

PSG provides comprehensive logging to help you monitor its operations and analyze performance:

*   **Console Output:** Real-time, color-coded updates on market data, signals, and trade actions.
*   **`logs/bot.log`:** A detailed log file capturing all console output, including debug messages (depending on logging level configured in `bot_logger.py`).
*   **`logs/trade_metrics.log`:** A separate log file dedicated to recording trade entry and exit details, as well as periodic summaries of overall trade statistics.

Regularly check these logs to understand the bot's behavior, debug issues, and review trade history.

## 🛠️ Extensibility & Customization

The modular design of PSG makes it relatively easy to extend and customize:

*   **Adding New Indicators:**
    *   Implement your new indicator logic within `indicators.py`.
    *   Call your new indicator function from `PSG.py` within `_initial_kline_fetch` and `_handle_kline_update` to calculate it on your `klines_df`.
    *   Pass the new indicator data to `strategy.py`.
*   **Modifying Strategies:**
    *   Adjust the logic within `strategy.py`'s `generate_signals` and `generate_exit_signals` functions.
    *   You can combine existing indicators in new ways or integrate newly added indicators.
    *   Experiment with different entry/exit conditions and risk management rules.
*   **Integrating Other Exchanges:**
    *   Create a new API client module similar to `bybit_api.py` for the desired exchange.
    *   Modify `PSG.py` to use the new client, ensuring it implements similar methods for fetching data, placing orders, and managing positions. This will require significant changes to the `PyrmethusBot` class.

## 🚧 Future Enhancements

*   **Advanced Order Block Logic:** Implement more sophisticated identification (e.g., mitigation, breaker blocks) and trading rules.
*   **Backtesting Module:** Develop a dedicated module to test strategies on historical data.
*   **Improved UI:** A more interactive or web-based UI for real-time monitoring and control.
*   **Advanced Risk Management:** Incorporate dynamic position sizing, maximum drawdown limits, and daily loss limits.
*   **Machine Learning Integration:** Explore using ML models for signal generation or market prediction.

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).

## 🧑‍💻 Code Care Steps

To ensure the longevity, maintainability, and collaborative development of Pyrmethus's Ultra Scalper Bot, please adhere to the following code care steps:

### 1. Code Style and Readability
*   **PEP 8 Compliance**: All Python code must follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) guidelines for maximum readability and consistency. Use linters like `flake8` or `pylint` to check compliance.
*   **Meaningful Naming**: Use descriptive names for variables, functions, classes, and modules. Avoid single-letter variables unless their context is immediately clear (e.g., `i` in a simple loop).
*   **Clear Comments**: Add comments to explain *why* a particular piece of code exists or *how* a complex algorithm works, rather than *what* it does (which should be evident from the code itself).
*   **Docstrings**: All functions, classes, and modules should have clear and concise docstrings explaining their purpose, arguments, and return values.
*   **Modular Design**: Keep functions and modules small and focused on a single responsibility. This improves readability, testability, and reusability.

### 2. Testing
*   **Unit Tests**: Write unit tests for individual functions and methods to ensure they work as expected. Use `pytest` for testing.
*   **Integration Tests**: Develop integration tests to verify the interaction between different modules and external services (e.g., Bybit API).
*   **Test Coverage**: Aim for high test coverage to minimize the risk of introducing bugs.
*   **Testnet First**: Always test new features and significant changes on a Bybit testnet account before deploying to a live account.

### 3. Version Control (Git)
*   **Atomic Commits**: Each commit should represent a single, logical change. Avoid committing unrelated changes together.
*   **Descriptive Commit Messages**: Write clear, concise, and informative commit messages. Follow a convention (e.g., Conventional Commits) if possible.
*   **Branching Strategy**: Use a clear branching strategy (e.g., Git Flow or GitHub Flow) for feature development, bug fixes, and releases.
*   **Regular Pull Requests**: Submit pull requests for all changes and ensure they are reviewed by at least one other developer before merging.

### 4. Error Handling and Robustness
*   **Specific Exceptions**: Catch specific exceptions rather than broad `Exception` types to handle errors more precisely.
*   **Graceful Degradation**: Design the bot to handle unexpected errors gracefully, logging them appropriately and attempting to recover or shut down safely without losing funds.
*   **Input Validation**: Validate all inputs, especially those coming from external sources (e.g., API responses, configuration files), to prevent unexpected behavior.
*   **Logging Levels**: Use appropriate logging levels (DEBUG, INFO, WARNING, ERROR, CRITICAL) to provide sufficient detail for debugging and monitoring without overwhelming the logs.

### 5. Dependencies and Environment
*   **`requirements.txt`**: Keep `requirements.txt` up-to-date with all project dependencies and their exact versions.
*   **Virtual Environments**: Always use virtual environments to manage project dependencies, isolating them from system-wide Python installations.
*   **Environment Variables**: Store sensitive information (API keys, secrets) in environment variables (`.env` file) and never commit them to version control.

### 6. Performance and Optimization
*   **Profiling**: Use Python's built-in profiling tools (`cProfile`) to identify performance bottlenecks in critical sections of the code.
*   **Asynchronous Best Practices**: Ensure `asyncio` is used effectively to prevent blocking operations and maximize concurrency.
*   **Decimal Usage**: Continue to use `Decimal` for all financial calculations to maintain precision and avoid floating-point errors.

By following these guidelines, we can collectively ensure that Pyrmethus's Ultra Scalper Bot remains a powerful, reliable, and maintainable tool for automated trading.