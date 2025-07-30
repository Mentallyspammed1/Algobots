Here's a detailed `README.md` file for your `PSG.py` project.

---

# Pyrmethus's Ultra Scalper Bot (PSG)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python Version">
  <img src="https://img.shields.io/badge/Bybit-API-orange.svg?style=for-the-badge&logo=bybit&logoColor=white" alt="Bybit API">
  <img src="https://img.shields.io/badge/Asyncio-Fast-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Asyncio">
  <img src="https://img.shields.io/badge/License-MIT-brightgreen.svg?style=for-the-badge" alt="License">
</p>

## 🚀 Overview

Pyrmethus's Ultra Scalper Bot (PSG) is an advanced, asynchronous cryptocurrency trading bot designed for scalping on the Bybit derivatives exchange. Leveraging a sophisticated strategy combining Fibonacci Pivot Points for dynamic support/resistance levels and Stochastic RSI for momentum analysis, PSG aims to capitalize on short-term price movements.

Built with `asyncio`, it ensures efficient, non-blocking operations, including real-time position management via WebSocket streams, robust API interaction with retry mechanisms, and comprehensive trade logging.

## ✨ Features

*   **Asynchronous Operation**: Fully non-blocking design using `asyncio` for high performance and responsiveness.
*   **Bybit Integration**: Connects to Bybit's derivatives API for seamless trading, including order placement, position management, and market data retrieval.
*   **Real-time Position Tracking**: Utilizes Bybit WebSockets to monitor and manage open positions with immediate updates, ensuring the bot's state is always synchronized with the exchange.
*   **Dynamic Strategy**:
    *   **Fibonacci Pivot Points**: Calculates dynamic support and resistance levels based on recent price action to identify potential reversal zones.
    *   **Stochastic RSI**: Employs Stochastic RSI for momentum and overbought/oversold condition analysis, with configurable crossover logic.
*   **Configurable Parameters**: All key trading parameters (symbols, intervals, trade amounts, indicator settings, SL/TP) are easily adjustable via `config.py`.
*   **Automated Trade Execution**: Automatically places market orders for entry and exit based on generated signals.
*   **Stop Loss & Take Profit**: Supports automated Stop Loss and Take Profit orders upon entry for risk management.
*   **Comprehensive Logging**: Detailed logging of bot activities, market data, signals, and trade executions, categorized by severity and color-coded for readability.
*   **Trade Metrics**: Tracks and reports key performance indicators like total PnL, win rate, average profit/loss per trade, and more.
*   **Robust Error Handling**: Implements retry mechanisms for API calls and graceful recovery from transient errors.
*   **Colorful Console Output**: Enhances readability with custom color coding for different log messages and market information.

## 🧠 How it Works (Strategy Overview)

The bot's core logic revolves around identifying entry and exit points using a combination of technical indicators:

1.  **Data Acquisition**: Periodically fetches the latest kline (candlestick) data from Bybit for the configured symbol and interval.
2.  **Indicator Calculation**:
    *   **Fibonacci Pivot Points**: Calculates a set of pivot points (Pivot, S1, S2, S3, R1, R2, R3) using the standard Fibonacci formulas based on the previous day's (or relevant period's) high, low, and close. These points act as potential support and resistance levels.
    *   **Stochastic RSI (StochRSI)**: Computes the StochRSI indicator, which measures the RSI relative to its high/low range over a set period. It generates two lines: %K and %D.
3.  **Signal Generation (`strategy.py`)**:
    *   **Entry Signals**:
        *   The bot looks for price action interacting with calculated Fibonacci support/resistance levels.
        *   Combined with StochRSI conditions (e.g., %K/%D crossing oversold/overbought levels, or %K crossing %D), it generates `BUY` or `SELL` signals. For instance, a `BUY` signal might occur if price is near a support level and StochRSI is oversold and crossing up.
    *   **Exit Signals**:
        *   If a position is open, the bot constantly monitors for exit conditions, which could include StochRSI reaching extreme overbought/oversold levels (opposite to entry conditions) or crossing against the position.
4.  **Trade Execution (`PSG.py`)**:
    *   **Entry**: If no position is open and an entry signal is detected, the bot calculates the appropriate order quantity based on `USDT_AMOUNT_PER_TRADE`, and places a market order along with configured Stop Loss and Take Profit levels.
    *   **Exit**: If a position is open and an exit signal is detected, the bot places a market order to close the entire position.
5.  **Position Synchronization**: The bot primarily relies on real-time WebSocket updates for its position state. This ensures that even if an order fills partially or in an unexpected way, the bot's internal state is always consistent with the exchange.
6.  **Continuous Monitoring**: The process loops indefinitely, fetching new data, recalculating indicators, and checking for signals at regular intervals (`POLLING_INTERVAL_SECONDS`).

## 🛠️ Prerequisites

Before you can run Pyrmethus's Ultra Scalper Bot, you'll need the following:

*   **Python 3.9+**: The bot is developed with modern Python features.
*   **Bybit Account**: A Bybit derivatives account (either mainnet or testnet).
*   **Bybit API Keys**: Generate API keys with appropriate permissions (Trade, Read Data). **Ensure you enable IP Whitelisting for enhanced security.**

## ⚙️ Installation

Follow these steps to get the bot up and running:

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/your-username/pyrmethus-scalper-bot.git
    cd pyrmethus-scalper-bot
    ```

2.  **Create a Virtual Environment (Recommended)**:
    ```bash
    python -m venv venv
    ```

3.  **Activate the Virtual Environment**:
    *   **On Windows**:
        ```bash
        .\venv\Scripts\activate
        ```
    *   **On macOS/Linux**:
        ```bash
        source venv/bin/activate
        ```

4.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
    (You'll need to create a `requirements.txt` file if you don't have one. It should contain `pandas`, `python-dotenv`, `pybit` or similar Bybit client library if used directly, or just the libraries you import. Given the code, `pandas` and `python-dotenv` are likely needed.)
    **Example `requirements.txt`:**
    ```
    pandas
    python-dotenv
    # If using the Bybit official client, it would be something like:
    # bybit-api
    # However, your code implies a custom 'bybit_api.py', so ensure its dependencies are met.
    # For websockets, you might need 'websockets' library if not handled by 'bybit_api.py' internally.
    ```

## 📝 Configuration

The bot's behavior is primarily controlled by two files: `.env` for sensitive API keys and `config.py` for trading parameters.

### 1. Environment Variables (`.env`)

Create a file named `.env` in the root directory of the project (same level as `PSG.py`). This file will store your Bybit API keys securely.

```dotenv
BYBIT_API_KEY=YOUR_BYBIT_API_KEY
BYBIT_API_SECRET=YOUR_BYBIT_API_SECRET
```

**Important:** Never share your `.env` file or commit it to version control.

### 2. Trading Parameters (`config.py`)

Open `config.py` and adjust the parameters according to your trading preferences and risk tolerance.

```python
# --- Trading Parameters ---
SYMBOL = "BTCUSDT"                  # Trading pair (e.g., "BTCUSDT", "ETHUSDT")
INTERVAL = "1"                      # Candle interval (e.g., "1", "5", "60", "D")
USDT_AMOUNT_PER_TRADE = 10.0        # USDT amount to use for each trade entry.
                                    # Bot calculates quantity based on current price.

# --- Fibonacci Pivot Point Settings ---
PIVOT_LEFT_BARS = 10                # Number of bars to the left for pivot detection
PIVOT_RIGHT_BARS = 10               # Number of bars to the right for pivot detection
PIVOT_TOLERANCE_PCT = 0.001         # Price tolerance percentage around pivot levels for signal generation

# --- Stochastic RSI Settings ---
STOCHRSI_K_PERIOD = 14              # StochRSI %K period
STOCHRSI_D_PERIOD = 3               # StochRSI %D period
STOCHRSI_OVERBOUGHT_LEVEL = 80      # Overbought threshold
STOCHRSI_OVERSOLD_LEVEL = 20        # Oversold threshold
USE_STOCHRSI_CROSSOVER = True       # If True, signals generated on %K/%D crossovers.
                                    # If False, signals generated when %K crosses over/under levels.

# --- Risk Management ---
STOP_LOSS_PCT = 0.005               # Percentage of entry price for stop loss (e.g., 0.005 for 0.5%)
                                    # Set to None to disable Stop Loss.
TAKE_PROFIT_PCT = 0.01              # Percentage of entry price for take profit (e.g., 0.01 for 1%)
                                    # Set to None to disable Take Profit.

# --- Bybit API Settings ---
BYBIT_API_ENDPOINT = "https://api-testnet.bybit.com" # Use "https://api.bybit.com" for mainnet
BYBIT_CATEGORY = "linear"           # Trading category: "linear" (USDT Perpetuals), "inverse"
CANDLE_FETCH_LIMIT = 200            # Number of historical candles to fetch for indicator calculations

# --- Bot Operational Settings ---
POLLING_INTERVAL_SECONDS = 10       # How often the bot fetches new data and checks for signals
API_REQUEST_RETRIES = 5             # Number of retries for failed API requests
API_BACKOFF_FACTOR = 0.5            # Factor for exponential backoff between API retries
```

## 🚀 Running the Bot

Once you have configured `config.py` and set up your `.env` file, you can run the bot:

1.  **Activate your virtual environment** (if not already active):
    *   Windows: `.\venv\Scripts\activate`
    *   macOS/Linux: `source venv/bin/activate`

2.  **Execute the main bot script**:
    ```bash
    python PSG.py
    ```

The bot will start, connect to Bybit, fetch market data, and begin monitoring for trading opportunities. You will see colored logs in your console indicating its operations, signals, and trade executions.

## 📁 Project Structure

```
pyrmethus-scalper-bot/
├── PSG.py                 # Main bot script, orchestrates all components.
├── config.py              # Configuration file for trading parameters and API settings.
├── indicators.py          # Contains functions for calculating technical indicators (e.g., StochRSI, Fibonacci Pivots).
├── strategy.py            # Defines the trading signal generation logic based on indicators.
├── bybit_api.py           # Custom asynchronous Bybit API client for REST and WebSocket interactions.
├── bot_logger.py          # Custom logging setup for colored and structured output.
├── trade_metrics.py       # Class to track and calculate trading performance metrics (PnL, win rate, etc.).
├── utils.py               # Utility functions (e.g., order quantity calculation).
├── color_codex.py         # Defines custom color codes for console output.
├── .env.example           # Example .env file for API keys (rename to .env).
├── .env                   # Your actual API keys (DO NOT COMMIT).
└── requirements.txt       # Python dependencies required for the project.
```

## 📊 Logging and Metrics

*   **Console Output**: The bot provides real-time, color-coded updates directly in your terminal, making it easy to follow its actions.
*   **Log Files**: Detailed logs are saved to files (configured in `bot_logger.py`, typically in a `logs/` directory). These logs include:
    *   General bot operations.
    *   API request/response details.
    *   Detected signals.
    *   Trade execution results.
    *   Errors and exceptions.
*   **Trade Metrics**: After each closed trade, the bot logs a summary of its overall performance, including:
    *   Total PnL (Profit and Loss).
    *   Number of winning/losing trades.
    *   Win rate.
    *   Average PnL per trade.
    *   Maximum drawdown (if implemented in `TradeMetrics`).

## ⚠️ Disclaimer

Trading cryptocurrencies involves substantial risk and is not suitable for all investors. The value of cryptocurrencies can fluctuate significantly, and you could lose your entire investment. This bot is provided for educational and informational purposes only. It is **not financial advice**. Always do your own research and only invest what you can afford to lose. The developers of this bot are not responsible for any financial losses incurred while using this software.

Before deploying to a live account, it is strongly recommended to:
*   **Thoroughly backtest** the strategy.
*   **Test extensively** on a Bybit testnet account.
*   **Understand all parameters** and their implications.

## 🤝 Contributing

Contributions are welcome! If you have suggestions, bug reports, or want to contribute code, please feel free to:

1.  Fork the repository.
2.  Create a new branch (`git checkout -b feature/your-feature-name`).
3.  Make your changes.
4.  Commit your changes (`git commit -m 'Add new feature'`).
5.  Push to the branch (`git push origin feature/your-feature-name`).
6.  Open a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---
