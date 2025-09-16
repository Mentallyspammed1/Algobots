# Bybit Automated Trading Bot

This project is an advanced automated trading bot designed for the Bybit exchange, leveraging the Bybit V5 API. It supports multiple trading strategies, robust error handling, dry-run simulations, and comprehensive logging to facilitate efficient and reliable cryptocurrency trading.

## ✨ Features

*   **Bybit V5 API Integration:** Full support for Bybit's latest API for market data, order management, and account information.
*   **Modular Strategy Design:** Easily integrate and manage multiple trading strategies.
*   **Dry Run Mode:** Simulate trades without risking real capital, perfect for testing and strategy validation.
*   **Robust Error Handling:** Implements retry mechanisms and graceful error management for API calls.
*   **Comprehensive Logging:** Detailed logging with `winston` for debugging, monitoring, and performance tracking.
*   **Real-time Data Processing:** Utilizes WebSockets for efficient market data consumption.
*   **Position and Order Management:** Advanced functions for placing, modifying, and canceling various order types (Market, Limit, Conditional) with integrated TP/SL.
*   **Account Management:** Fetches balance and position information.

## 🚀 Prerequisites

Before you begin your journey, ensure you have the following installed:

*   **Node.js (v18 or higher):** The runtime environment for the bot.
*   **npm (Node Package Manager):** Used for managing project dependencies.

## 🛠️ Installation

To set up the bot, follow these ancient steps:

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/javabot.git
    cd javabot
    ```
2.  **Install dependencies:**
    ```bash
    npm install
    ```

## ⚙️ Configuration

The bot's behavior is governed by two sacred scrolls: `.env` for sensitive credentials and `config.js` for operational settings.

### `.env` File

Create a `.env` file in the project root with your Bybit API credentials:

```
BYBIT_API_KEY=YOUR_BYBIT_API_KEY
BYBIT_API_SECRET=YOUR_BYBIT_API_SECRET
```

**WARNING:** Never commit your `.env` file to version control!

### `config.js` File

The `config.js` file (or `config.yaml` if you prefer YAML) contains all other configurable parameters, including:

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

## 🚀 How to Run

To summon the bot's power, execute the orchestrator:

```bash
npm start
```

This will initiate `bot_orchestrator.js`, which in turn will load and run all enabled strategies defined in `config.js`.

## 🧪 Testing

To ensure the bot's spells are potent and true, run the test suite:

```bash
npm test
```

This will execute tests defined in the `tests/` directory using Jest.

## 🏛️ Architecture Overview

The bot follows a modular architecture, designed for scalability and maintainability:

*   **`bot_orchestrator.js`:** The central command, responsible for loading and initiating active trading strategies.
*   **`bybit_api_client.js`:** Encapsulates all interactions with the Bybit V5 REST API, providing a robust and retriable interface.
*   **`bybit_api.js`:** (Potentially deprecated or merged into `bybit_api_client.js` - needs clarification)
*   **`strategies/`:** Contains individual trading strategy modules. Each strategy is designed to be self-contained and can be enabled/disabled via `config.js`.
*   **`indicators.js`:** Houses technical indicator calculations used by various strategies.
*   **`logger.js`:** Provides a centralized and colored logging mechanism using `winston`.
*   **`utils/`:** A collection of utility functions (e.g., `math_utils.js`, `websocket_client.js`, `alert_system.js`).
*   **`config.js`:** The global configuration file.

## ❓ Troubleshooting and FAQ

*   **`API Key and Secret must be provided` error:** Ensure your `BYBIT_API_KEY` and `BYBIT_API_SECRET` are correctly set in the `.env` file.
*   **`TypeError: chalk.purple is not a function`:** The `chalk` library does not have a `purple` method. Use `chalk.magenta`, `chalk.rgb(R,G,B)`, or `chalk.hex('#RRGGBB')` instead.
*   **Bot not placing trades:** Check if `DRY_RUN` is set to `true` in `config.js`. Set it to `false` to enable live trading. Also, verify your API keys have trading permissions.
*   **Strategy not starting:** Ensure the strategy is `enabled: true` in `config.js` and that its module exists in the `strategies/` directory.
*   **`Bybit API Error 10001: accountType only support UNIFIED`:** Your Bybit account must be a Unified Trading Account (UTA). Upgrade your account in Bybit settings.

---
