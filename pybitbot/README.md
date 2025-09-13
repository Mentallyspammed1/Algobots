# Bybit Algobots: Unified Supertrend Trading Bot

This repository is being refactored to contain a professional-grade, fully asynchronous trading bot designed for the Bybit exchange. It implements advanced Supertrend-based strategies, with a strong focus on scalping, robust risk management, and real-time data processing, all unified into a single, modular codebase.

## ✨ Key Features

*   **Unified & Modular Architecture**: Consolidates multiple bot versions into a single, extensible framework with clear separation of concerns (clients, strategies, risk management, persistence).
*   **Fully Asynchronous Core**: Built on `asyncio` for high-performance, non-blocking operations.
*   **Pluggable Strategies**: Supports various Supertrend-based strategies (e.g., Ehlers Supertrend Cross) via a flexible strategy pattern.
*   **Real-time Data**: Utilizes Bybit WebSockets for live market data (kline updates) with robust reconnection logic.
*   **Precision Trading**: Employs Python's `decimal.Decimal` for accurate financial calculations, mitigating floating-point errors.
*   **Comprehensive Risk Management**: Implements fixed-risk position sizing, dynamic trailing stop-loss, and emergency stop mechanisms.
*   **Intelligent Order Management**: Handles market and limit orders with dynamic SL/TP levels, and robust position adjustment logic.
*   **State Persistence & Recovery**: Designed to save and load critical bot state, enabling seamless restarts.
*   **Dynamic Precision Handling**: Automatically fetches and applies market-specific price and quantity precision from Bybit.
*   **Configurable**: Centralized configuration (`config/config.py`) for easy customization of API settings, trading parameters, and strategy specifics.
*   **Comprehensive Logging**: Detailed, color-coded logging for all critical operations, providing immediate visual feedback and facilitating debugging.

## 🚀 Getting Started

### Prerequisites

*   Python 3.8+
*   `pip` (Python package installer)
*   A Bybit account (Unified Trading Account recommended for full compatibility).

### Installation

1.  **Clone the repository (if applicable):**
    ```bash
    git clone <repository_url>
    cd pybitbot
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: A `requirements.txt` will be generated/updated during the refactoring process. For now, ensure `pybit`, `pandas`, `numpy`, `python-dotenv`, `tenacity`, `pytest`, `pytest-asyncio` are installed.)*

### Configuration

1.  **Create a `.env` file**: In the `pybitbot/` directory, create a file named `.env`.

2.  **Add your Bybit API credentials**: Open the `.env` file and add your API key and secret. **Never share these credentials or commit them to version control.**
    ```
    BYBIT_API_KEY="YOUR_API_KEY"
    BYBIT_API_SECRET="YOUR_API_SECRET"
    ```
    *Replace `YOUR_API_KEY` and `YOUR_API_SECRET` with your actual Bybit API credentials.*

3.  **Configure the bot**: Open `config/config.py` and modify the parameters to suit your trading preferences. Key parameters include:
    *   `api.TESTNET`: Set to `True` for testing on Bybit's testnet, `False` for live trading.
    *   `SYMBOL`: The trading pair (e.g., `XLMUSDT`, `BTCUSDT`).
    *   `TIMEFRAME`: The candlestick interval for the strategy (e.g., `"1"`, `"3"`, `"5"` for scalping).
    *   `strategy_settings`: A section for specific parameters for your chosen strategy.

### Running the Bot

Once refactoring is complete, the bot will be runnable via a single entry point:

```bash
python3 main.py # (Conceptual entry point after refactoring)
```

## ⚠️ Important Notes

*   **Refactoring in Progress**: This repository is currently undergoing significant refactoring to consolidate multiple bot versions. The structure and entry points described above are the target architecture.
*   **Risk Management**: Automated trading carries significant risks. Ensure you understand the risk parameters configured.
*   **API Keys**: Keep your API keys secure. Enable IP whitelisting on your Bybit account for added security.
*   **Unified Trading Account (UTA)**: The bot is designed to work with Bybit's Unified Trading Account. If you encounter `Error 10001: accountType only support UNIFIED`, please upgrade your Bybit account to UTA.
*   **Backtesting**: Thorough backtesting of your chosen strategy parameters on historical data is highly recommended before deploying with real funds.
*   **Monitoring**: Always monitor the bot's performance and logs closely, especially during initial deployment.

## 🧪 Testing

Unit tests are being developed to verify core functionalities and indicator calculations. Tests are located in the `tests/` directory.

To run tests (requires `pytest` and `pytest-asyncio`):

```bash
pytest pybitbot/tests/
```

## 🤝 Contributing

Contributions are welcome! Please refer to the `TODO.txt` for planned improvements and `GEMINI.md` for detailed architectural insights.