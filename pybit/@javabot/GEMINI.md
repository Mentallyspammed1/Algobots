# Vabot - A Modular Bybit Trading Bot in Node.js

This project contains a collection of Node.js-based trading bots designed to operate on the Bybit exchange. The bots utilize various technical analysis strategies to generate trading signals and manage positions. The presence of multiple entry-point scripts (`chanexit.js`, `ehlst.js`, `est.js`) suggests an evolution of strategies and implementations.

## Project Structure & Core Components

The `javabot` directory contains three distinct bot implementations, each with its own logic and dependencies.

| File | Strategy | Key Features & Approach | Primary Dependencies |
| :--- | :--- | :--- | :--- |
| **`chanexit.js`** | **Advanced Multi-Filter Strategy** | - **Entry:** EMA crossover with Higher-TF trend, RSI, Volume, and optional (mocked) EST, Stoch, MACD, ADX filters.<br>- **Exit:** Manages exits via Fixed Profit, Trailing Stop (Chandelier), Fisher Transform flip, and Time-based stops.<br>- **Persistence:** Uses **SQLite** to track trades for resilience.<br>- **Data Handling:** Uses `dataframe-js` for data manipulation.<br>- **Robustness:** Features position reconciliation and equity-based emergency stop. | `@bybit-api/client`, `moment-timezone`, `sqlite3`, `dataframe-js`, `uuid` |
| **`ehlst.js`** | **Ehlers Supertrend Cross** | - **Entry:** Crossover of fast and slow Supertrend, confirmed by Ehlers Fisher Transform, RSI, and volume.<br>- **API Client:** Implements a **manual Bybit client** using `axios` and `crypto-js`.<br>- **Logging:** Contains a custom-built ANSI color logger. | `axios`, `crypto-js`, `luxon`, `technicalindicators`, `js-yaml` |
| **`est.js`** | **Ehlers Supertrend Cross** | - **Entry:** Similar logic to `ehlst.js`, based on Supertrend, Fisher, and RSI.<br>- **API Client:** Uses the standard **`@bybit-api/client`** library for exchange interaction.<br>- **Logging:** Uses the standard `chalk` library for colored output. | `@bybit-api/client`, `chalk`, `technicalindicators`, `js-yaml` |

---

## Architecture and Design

-   **Configuration**: All bots are driven by a central `config.yaml` file, which should be present in the same directory. This file defines trading symbols, strategy parameters, and risk management settings.
-   **API Interaction**: The project showcases two methods of API interaction:
    1.  A manual, from-scratch REST client (`ehlst.js`).
    2.  The recommended approach using the official `@bybit-api/client` library (`chanexit.js`, `est.js`).
-   **State Management**: `chanexit.js` is the most advanced script, featuring an SQLite database (`scalper_positions.sqlite`) for persistent trade tracking. This allows the bot to recover from restarts and reconcile its state with the exchange.
-   **Technical Analysis**: Indicators are calculated primarily using the `technicalindicators` library. However, `chanexit.js` notes that several of its more advanced indicators are currently mocked and would require a full implementation to be effective.

---

## Setup and Usage

### 1. Install Dependencies

Navigate to the `javabot` directory and install the required Node.js packages.

```bash
cd /data/data/com.termux/files/home/Algobots/pybit/javabot/
npm install
```

### 2. Set API Credentials

The bots read Bybit API credentials from environment variables. You must set them in your shell:

```bash
export BYBIT_API_KEY="YOUR_API_KEY"
export BYBIT_API_SECRET="YOUR_API_SECRET"
```

**Note**: If these variables are not set, the bots will automatically enforce `dry_run = true` as a safety measure.

### 3. Configure the Bot

Create and edit a `config.yaml` file in the `javabot` directory to define your trading strategy, symbols, and risk parameters.

### 4. Run a Bot

You can run any of the bot scripts using Node.js.

```bash
# To run the most feature-rich bot with persistence
node chanexit.js

# To run the Ehlers Supertrend strategy (axios version)
node ehlst.js

# To run the Ehlers Supertrend strategy (bybit-api client version)
node est.js
```

---

## Key Dependencies

-   `@bybit-api/client`: The official Bybit V5 API client.
-   `axios` & `crypto-js`: Used for manual REST API requests and signing.
-   `chalk` & `luxon` & `moment-timezone`: For colored logging and time/date manipulation.
-   `js-yaml`: For parsing the `config.yaml` file.
-   `sqlite` & `sqlite3`: For database-driven position tracking.
-   `technicalindicators`: For calculating TA indicators like Supertrend, RSI, etc.
-   `dataframe-js`: For advanced data manipulation.
-   `uuid`: For generating unique IDs.

## Areas for Improvement

-   **Consolidation**: The three separate bot files could be refactored into a single, modular application where the strategy is selectable via the configuration file.
-   **Indicator Implementation**: The mocked indicators in `chanexit.js` should be fully implemented for the strategy to function as designed.
-   **Standardization**: The manual API client and logger in `ehlst.js` could be replaced with `@bybit-api/client` and `chalk` to standardize the codebase.
