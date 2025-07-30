Here's a detailed `README.md` file for your `PSG.py` project.

---

# Pyrmethus's Ultra Scalper Bot (PSG) - Transmuted

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python Version">
  <img src="https://img.shields.io/badge/Bybit-API-orange.svg?style=for-the-badge&logo=bybit&logoColor=white" alt="Bybit API">
  <img src="https://img.shields.io/badge/Asyncio-Fast-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Asyncio">
  <img src="https://img.shields.io/badge/License-MIT-brightgreen.svg?style=for-the-badge" alt="License">
</p>

## 🚀 Overview

Pyrmethus's Ultra Scalper Bot (PSG) is an advanced, asynchronous cryptocurrency trading bot designed for scalping on the Bybit derivatives exchange. It has been significantly enhanced to incorporate high-precision mathematics and a more resilient architecture. Leveraging a sophisticated strategy combining Fibonacci Pivot Points, Stochastic RSI, and Average True Range (ATR), PSG aims to capitalize on short-term price movements.

Built with `asyncio`, it ensures efficient, non-blocking operations, including real-time position management via WebSocket streams, robust API interaction with retry mechanisms, and comprehensive trade logging.

## ✨ Features

*   **Asynchronous Operation**: Fully non-blocking design using `asyncio` for high performance and responsiveness.
*   **Bybit Integration**: Connects to Bybit's derivatives API for seamless trading, including order placement, position management, and market data retrieval.
*   **High-Precision Calculations**: Utilizes Python's `Decimal` type for all price and quantity calculations, eliminating floating-point inaccuracies.
*   **Real-time Position Tracking**: Utilizes Bybit WebSockets to monitor and manage open positions with immediate updates, ensuring the bot's state is always synchronized with the exchange.
*   **Dynamic Strategy**:
    *   **Fibonacci Pivot Points**: Calculates dynamic support and resistance levels based on recent price action.
    *   **Stochastic RSI**: Employs Stochastic RSI for momentum and overbought/oversold condition analysis.
    *   **Average True Range (ATR)**: Calculates ATR to measure market volatility.
*   **Dynamic Risk Management**: Automatically sets and adjusts Take Profit and Stop Loss orders for open positions via the `set_trading_stop` API endpoint, reacting in real-time to market changes.
*   **Configurable Parameters**: All key trading parameters are easily adjustable via `config.py`.
*   **Automated Trade Execution**: Automatically places market orders for entry and exit based on generated signals.
*   **Comprehensive Logging**: Detailed logging of bot activities, market data, signals, and trade executions, categorized by severity and color-coded for readability.
*   **Trade Metrics**: Tracks and reports key performance indicators like total PnL, win rate, and more.
*   **Robust Error Handling**: Implements retry mechanisms for API calls and graceful recovery from transient errors.
*   **Colorful Console Output**: Enhances readability with custom color coding for different log messages and market information.

## 🧠 How it Works (Strategy Overview)

The bot's core logic revolves around identifying entry and exit points using a combination of technical indicators:

1.  **Data Acquisition**: Periodically fetches the latest kline (candlestick) data from Bybit.
2.  **Indicator Calculation**: Calculates Fibonacci Pivot Points, Stochastic RSI, and ATR.
3.  **Signal Generation (`strategy.py`)**: Generates `BUY` or `SELL` signals based on the confluence of the indicators.
4.  **Trade Execution (`PSG.py`)**: Places market orders for entry and exit based on signals.
5.  **Position Synchronization**: Relies on real-time WebSocket updates for its position state. When a position is opened or modified, the bot automatically sets/updates the Take Profit and Stop Loss on the exchange.
6.  **Continuous Monitoring**: The process loops indefinitely, fetching new data, recalculating indicators, and checking for signals.

## 🛠️ Prerequisites

*   **Python 3.9+**
*   **Bybit Account**
*   **Bybit API Keys**

## ⚙️ Installation

1.  **Clone the Repository**
2.  **Create a Virtual Environment**
3.  **Activate the Virtual Environment**
4.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
    **Example `requirements.txt`:**
    ```
    pandas
    python-dotenv
    websockets
    httpx
    ```

## 📝 Configuration

### 1. Environment Variables (`.env`)

Create a file named `.env` in the root directory:
```dotenv
BYBIT_API_KEY=YOUR_BYBIT_API_KEY
BYBIT_API_SECRET=YOUR_BYBIT_API_SECRET
```

### 2. Trading Parameters (`config.py`)

Adjust parameters in `config.py` to your preferences.

## 🚀 Running the Bot

```bash
python PSG.py
```

## 📁 Project Structure

```
pyrmethus-scalper-bot/
├── PSG.py
├── config.py
├── indicators.py
├── strategy.py
├── bybit_api.py
├── bot_logger.py
├── trade_metrics.py
├── utils.py
├── color_codex.py
├── .env
└── requirements.txt
```

## 📊 Logging and Metrics

*   **Console Output**: Real-time, color-coded updates.
*   **Log Files**: Detailed logs are saved to files.
*   **Trade Metrics**: After each closed trade, the bot logs a summary of its overall performance.

## ⚠️ Disclaimer

Trading cryptocurrencies involves substantial risk. This bot is for educational purposes only and is not financial advice. Test extensively on a testnet account before using real funds.

## 🤝 Contributing

Contributions are welcome! Please fork the repository and open a pull request.

## 📄 License

This project is licensed under the MIT License.

---