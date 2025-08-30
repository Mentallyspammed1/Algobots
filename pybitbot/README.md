# Bybit Algobots: Supertrend & Ehlers Supertrend Cross Trading Bot

This repository contains a professional-grade, fully asynchronous trading bot designed for the Bybit exchange. It implements advanced Supertrend-based strategies, with a strong focus on scalping, robust risk management, and real-time data processing.

## ✨ Key Features

*   **Fully Asynchronous Core**: Built entirely on `asyncio` for high-performance, non-blocking operations.
*   **Modular & Extensible Architecture**: Cleanly separated components for configuration, market data, positions, strategies, and bot execution, allowing for easy expansion and maintenance.
*   **State Persistence & Recovery**: Automatically saves and loads critical bot state (`bot_state.pkl`), enabling seamless restarts without losing context of open positions or pending signals.
*   **Advanced Strategy Implementation**: Features the **Ehlers Supertrend Cross Strategy**, specifically tuned for scalping. This strategy utilizes a custom recursive low-pass filter (eliminating external scientific libraries like SciPy) for highly responsive trend identification.
*   **Comprehensive Risk Management**: Implements fixed-risk position sizing, dynamic trailing stop-loss with break-even activation, and robust Decimal handling for precise financial calculations.
*   **Intelligent Order Management**: Supports market and limit orders with strategy-defined Stop-Loss (SL) and Take-Profit (TP) levels. Includes intelligent trailing stops and robust logic for reversing or adjusting existing positions based on new signals.
*   **Robust WebSocket Handling**: Dedicated manager for WebSocket connections ensures high uptime with automatic reconnection and exponential backoff.
*   **Dynamic Precision Handling**: Automatically fetches and applies market-specific price and quantity precision from Bybit, minimizing order rejection errors.
*   **Enhanced Entry/Exit Logic**: Incorporates tunable signal confirmation, dynamic take-profit calculation, and intelligent position sizing based on calculated risk and stop-loss distance.
*   **Vibrant Neon Console Logging**: Detailed, color-coded logging for all critical operations, providing immediate visual feedback and facilitating debugging.

## 🚀 Getting Started

### Prerequisites

*   Python 3.8+
*   A Bybit account (Unified Trading Account recommended for full compatibility).

### Installation

1.  **Clone the repository (if applicable):**
    ```bash
    git clone <repository_url>
    cd pybitbot
    ```

2.  **Install dependencies:**
    ```bash
    pip install pybit pandas numpy python-dotenv pytz aiofiles
    ```

### Configuration

1.  **Create a `.env` file**: In the root directory of the bot (e.g., `/data/data/com.termux/files/home/Algobots/pybitbot/`), create a file named `.env`.

2.  **Add your Bybit API credentials**: Open the `.env` file and add your API key and secret. **Never share these credentials or commit them to version control.**
    ```
    BYBIT_API_KEY="YOUR_API_KEY"
    BYBIT_API_SECRET="YOUR_API_SECRET"
    ```
    *Replace `YOUR_API_KEY` and `YOUR_API_SECRET` with your actual Bybit API credentials.*

3.  **Configure the bot**: Open the main bot script (e.g., `ehlers_stcx.py` or `supertrend_bot.py` depending on which version you intend to run) and modify the `Config` class parameters to suit your trading preferences. Key parameters include:
    *   `testnet`: Set to `True` for testing on Bybit's testnet, `False` for live trading.
    *   `symbol`: The trading pair (e.g., `XLMUSDT`, `BTCUSDT`).
    *   `category`: `"linear"` for USDT Perpetuals, `"inverse"` for Inverse Perpetuals.
    *   `risk_per_trade_pct`: Percentage of equity to risk per trade (e.g., `0.005` for 0.5%).
    *   `leverage`: Desired leverage for trades.
    *   `timeframe`: The candlestick interval for the strategy (e.g., `"1"`, `"3"`, `"5"` for scalping).
    *   `strategy_name`: Choose between `"Supertrend"` (classic) or `"EhlersSupertrendCross"` (recommended for scalping).
    *   `strategy_params`: A dictionary containing specific parameters for your chosen strategy (e.g., `supertrend_period`, `supertrend_multiplier`, `ehlers_filter_alpha`, `take_profit_atr_multiplier`, `signal_confirmation_candles`). These are pre-tuned for scalping in `ehlers_stcx.py`.

### Running the Bot

Navigate to the bot's directory in your terminal and execute the desired script:

```bash
python3 ehlers_stcx.py
# Or if you prefer the original supertrend_bot.py
# python3 supertrend_bot.py
```

## ⚠️ Important Notes

*   **Risk Management**: Automated trading carries significant risks. Ensure you understand the `risk_per_trade_pct` and `leverage` settings. Never risk more than you can afford to lose.
*   **API Keys**: Keep your API keys secure. Enable IP whitelisting on your Bybit account for added security.
*   **Unified Trading Account (UTA)**: The bot is designed to work with Bybit's Unified Trading Account. If you encounter `Error 10001: accountType only support UNIFIED`, please upgrade your Bybit account to UTA.
*   **Backtesting**: While the bot is designed for live trading, thorough backtesting of your chosen strategy parameters on historical data is highly recommended before deploying with real funds.
*   **Monitoring**: Always monitor the bot's performance and logs (`supertrend_bot.log`) closely, especially during initial deployment.

## 🧪 Testing

Unit tests are available in `test_supertrend_bot.py` to verify the core logic of the `supertrend_bot.py` implementation. To run the tests:

```bash
python3 -m unittest test_supertrend_bot.py
```

## 🤝 Contributing

Contributions are welcome! Please feel free to fork the repository, make improvements, and submit pull requests.
