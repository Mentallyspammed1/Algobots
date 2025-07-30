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

*   **Real-time Data Processing**: Utilizes Bybit WebSocket APIs for live kline and position updates, ensuring immediate reaction to market changes.
*   **Multi-Indicator Strategy**:
    *   **Stochastic RSI**: Identifies overbought/oversold conditions and potential reversals, with optional crossover confirmation.
    *   **Fibonacci Pivot Points**: Calculates dynamic support and resistance levels based on a configurable higher timeframe, used for entry/exit confluence.
    *   **Order Block Identification (Initial):** Tracks potential supply/demand zones based on pivot highs/lows for future strategy integration.
    *   **ATR, SMA, Ehlers Fisher Transform, Ehlers Super Smoother**: Additional indicators for market analysis and potential future strategy enhancements.
*   **Dynamic Position Management**:
    *   **Flexible Entry/Exit**: Executes market orders for quick entries and exits based on generated signals.
    *   **Automatic TP/SL**: Sets Take Profit and Stop Loss orders based on configurable percentages or dynamic ATR multipliers.
    *   **Robust State Tracking**: Maintains accurate internal state of open positions, entry prices, and PnL, synchronized with exchange data via WebSockets.
*   **Precision & Reliability**:
    *   **Decimal Arithmetic**: Uses Python's `Decimal` type for all financial calculations to prevent floating-point inaccuracies.
    *   **Error Handling & Retries**: Implements retry mechanisms for API requests and robust exception handling for continuous operation.
*   **Comprehensive Logging**: Detailed logging of bot actions, trade executions, market data, and performance metrics for analysis and debugging.
*   **Modular Architecture**: Clean separation of concerns (API interaction, indicators, strategy, logging, UI) for easy maintenance and extensibility.
*   **Configurable Parameters**: All key trading parameters are externalized in `config.py` and `.env` for easy customization.

## 🧠 How it Works (Strategy Overview)

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
