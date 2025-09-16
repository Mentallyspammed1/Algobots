# Bybit Automated Trading Bot

This project is an advanced automated trading bot designed for the Bybit exchange, leveraging the Bybit V5 API. It supports multiple trading strategies in both Python and Node.js, robust error handling, dry-run simulations, and comprehensive logging to facilitate efficient and reliable cryptocurrency trading.

## ✨ Features

*   **Bybit V5 API Integration:** Full support for Bybit's latest API for market data, order management, and account information.
*   **Modular Strategy Design:** Easily integrate and manage multiple trading strategies in both Python and Node.js.
*   **Dual Language Support:** Run bots in either Node.js or Python, depending on your preference and strategy.
*   **Dry Run Mode:** Simulate trades without risking real capital, perfect for testing and strategy validation.
*   **Robust Error Handling:** Implements retry mechanisms and graceful error management for API calls.
*   **Comprehensive Logging:** Detailed logging with `winston` (Node.js) and `logging` (Python) for debugging, monitoring, and performance tracking.
*   **Real-time Data Processing:** Utilizes WebSockets for efficient market data consumption.
*   **Position and Order Management:** Advanced functions for placing, modifying, and canceling various order types (Market, Limit, Conditional) with integrated TP/SL.
*   **Account Management:** Fetches balance and position information.

## 🚀 Prerequisites

Before you begin your journey, ensure you have the following installed:

*   **Node.js (v18 or higher):** The runtime environment for the Node.js bots.
*   **npm (Node Package Manager):** Used for managing Node.js project dependencies.
*   **Python (3.9 or higher):** The runtime environment for the Python bots.
*   **pip:** Used for managing Python project dependencies.

## 🛠️ Installation

To set up the bot, follow these ancient steps:

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/javabot.git
    cd javabot
    ```
2.  **Install Node.js dependencies:**
    ```bash
    npm install
    ```
3.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## ⚙️ Configuration

The bot's behavior is governed by a set of configuration files.

### Credentials

Create a `.env` file in the project root with your Bybit API credentials:

```
BYBIT_API_KEY=YOUR_BYBIT_API_KEY
BYBIT_API_SECRET=YOUR_BYBIT_API_SECRET
```

**WARNING:** Never commit your `.env` file to version control!

### Node.js Bot Configuration

The Node.js bots are configured using `config.js`. This file contains all other configurable parameters, including:

*   **API Settings:** `TESTNET`, `DRY_RUN` flags.
*   **Logging Settings:** Log levels, file paths.
*   **Strategy Definitions:** Enable/disable strategies and their specific parameters.
*   **Retry Mechanisms:** `ORDER_RETRY_ATTEMPTS`, `ORDER_RETRY_DELAY_SECONDS`.

**Example `config.js` structure:**

```javascript
export const CONFIG = {
    API_KEY: process.env.BYBIT_API_KEY || '',
    API_SECRET: process.env.BYBIT_API_SECRET || '',
    TESTNET: true, // Set to false for live trading
    DRY_RUN: true, // Set to false to enable actual trades

    // ... other configurations

    STRATEGIES: {
        ehlst_strategy: {
            enabled: true,
            symbol: 'BTCUSDT',
            interval: '1', // 1-minute klines
            leverage: 10,
            // ... strategy-specific parameters
        },
        market_maker_strategy: {
            enabled: false,
            // ...
        }
    },

    // ... more settings
};
```

### Python Bot Configuration

The Python bots are configured via a `config.py` file. This file defines which strategy to use.

**Example `config.py`:**
```python
# config.py
STRATEGY_FILE = "strategies/stochrsi_fib_ob_strategy.py"
```

## 🚀 How to Run

### Running the Node.js Bot

To summon the Node.js bot's power, execute the orchestrator:

```bash
npm start
```

This will initiate `bot_orchestrator.js`, which in turn will load and run all enabled strategies defined in `config.js`.

### Running the Python Bot

To run the main Python bot, execute:
```bash
python main.py
```
This will start the `BybitTrader` with the strategy defined in `config.py`.


## 🧪 Testing

To ensure the bot's spells are potent and true, run the test suite:

```bash
npm test
```

This will execute tests defined in the `tests/` directory using Jest.

## 🏛️ Architecture Overview

The bot follows a modular architecture, designed for scalability and maintainability.

### Node.js Architecture

*   **`bot_orchestrator.js`:** The central command for Node.js bots, responsible for loading and initiating active trading strategies.
*   **`bybit_api_client.js`:** Encapsulates all interactions with the Bybit V5 REST API for Node.js.
*   **`strategies/`:** Contains individual trading strategy modules for Node.js.
*   **`indicators.js`:** Houses technical indicator calculations for Node.js strategies.
*   **`logger.js`:** Provides a centralized logging mechanism using `winston`.
*   **`utils/`:** A collection of utility functions for the Node.js bots.
*   **`config.js`:** The global configuration file for Node.js bots.

### Python Architecture

*   **`main.py`:** The main entry point for the Python bots.
*   **`bybit_trader.py`:** The core of the Python bot, handling the trading logic.
*   **`strategies/`:** Contains individual trading strategy modules for Python.
*   **`indicators.py`:** Houses technical indicator calculations for Python strategies.
*   **`bot_logger.py`:** Provides a centralized logging mechanism for Python.
*   **`config.py`:** The configuration file for Python bots.


## ❓ Troubleshooting and FAQ

*   **`API Key and Secret must be provided` error:** Ensure your `BYBIT_API_KEY` and `BYBIT_API_SECRET` are correctly set in the `.env` file.
*   **`TypeError: chalk.purple is not a function`:** The `chalk` library does not have a `purple` method. Use `chalk.magenta`, `chalk.rgb(R,G,B)`, or `chalk.hex('#RRGGBB')` instead.
*   **Bot not placing trades:** Check if `DRY_RUN` is set to `true` in `config.js`. Set it to `false` to enable live trading. Also, verify your API keys have trading permissions.
*   **Strategy not starting:** Ensure the strategy is `enabled: true` in `config.js` and that its module exists in the `strategies/` directory.
*   **`Bybit API Error 10001: accountType only support UNIFIED`:** Your Bybit account must be a Unified Trading Account (UTA). Upgrade your account in Bybit settings.