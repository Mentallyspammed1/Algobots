# Whalebot Trading Bot Agents

Whalebot is an advanced algorithmic trading bot designed for the Bybit cryptocurrency exchange. It leverages a comprehensive suite of technical indicators, multi-timeframe analysis, and optional machine learning models to identify and execute trading opportunities.

## Core Components

1.  **Bybit Client (`BybitClient`)**:
    *   Handles all communication with the Bybit API.
    *   Manages API key authentication, request signing, and rate limiting.
    *   Fetches market data such as ticker prices, klines (candlestick data), and order books.
    *   Supports both public and signed API endpoints.

2.  **Configuration Management (`load_config`)**:
    *   Loads trading parameters, API keys, and indicator settings from `config.json`.
    *   Provides a default configuration if the file is not found.
    *   Includes validation to ensure critical parameters are correctly set.
    *   Supports customizable indicator weights and settings for different trading strategies (e.g., `default_scalping`).

3.  **Logger (`setup_logger`)**:
    *   Configures logging to both the console and a rotating file.
    *   Uses a `SensitiveFormatter` to redact API keys and secrets in log messages.
    *   Provides different log levels (INFO, DEBUG, ERROR, WARNING) for detailed monitoring.

4.  **Trading Analyzer (`TradingAnalyzer`)**:
    *   The heart of the bot's analytical engine.
    *   Calculates a wide array of technical indicators based on the provided historical price data (`pandas.DataFrame`).
    *   Supports indicators like:
        *   **Trend Following**: Moving Averages (SMA, EMA), Ehlers SuperTrend, Ichimoku Cloud, PSAR, VWMA, DEMA, Keltner Channels.
        *   **Momentum**: RSI, Stochastic RSI, MACD, CCI, Williams %R, MFI, ROC, Kaufman AMA.
        *   **Volume**: OBV, CMF, Volume Delta, Relative Volume.
        *   **Volatility**: ATR, Bollinger Bands.
        *   **Market Structure**: Trend identification based on recent highs and lows.
        *   **Fibonacci**: Retracement levels and Pivot Points.
    *   Applies weights to different indicators based on the selected strategy (`weight_sets` in config) to generate a consolidated trading signal.
    *   Integrates Multi-Timeframe (MTF) analysis to assess trends on higher timeframes.
    *   Calculates a `signal_score` and determines the final trading signal (BUY, SELL, HOLD).

5.  **Position Manager (`PositionManager`)**:
    *   Manages the bot's open trades.
    *   Calculates optimal order sizes based on account balance, risk per trade, and ATR.
    *   Handles the logic for opening new positions (BUY/SELL).
    *   Monitors open positions and closes them when Stop Loss or Take Profit levels are hit, or based on trailing stop logic.
    *   Respects `max_open_positions` and other trade management parameters defined in the configuration.

6.  **Performance Tracker (`PerformanceTracker`)**:
    *   Records all executed trades, including entry/exit prices, PnL, and reasons for closure (Stop Loss, Take Profit).
    *   Calculates overall performance metrics like total PnL, win rate, and number of wins/losses.
    *   Accounts for trading fees and slippage in PnL calculations.

7.  **Alert System (`AlertSystem`)**:
    *   Provides a standardized way to send alerts (INFO, WARNING, ERROR) through the logger.
    *   Can be extended to integrate with external notification services (e.g., Telegram, Discord, email).

## Workflow

1.  **Initialization**:
    *   Setup logger.
    *   Load configuration (`config.json`).
    *   Initialize `BybitClient`, `PositionManager`, `PerformanceTracker`, `AlertSystem`.

2.  **Main Loop (`while True`)**:
    *   Fetch current market price.
    *   Fetch historical klines for the primary trading interval.
    *   (Optional) Fetch order book data if `orderbook_imbalance` is enabled.
    *   (Optional) Fetch klines for higher timeframes (MTF analysis) if enabled.
    *   Instantiate `TradingAnalyzer` with the fetched data.
    *   Calculate all enabled technical indicators.
    *   Generate a trading signal (`BUY`, `SELL`, `HOLD`) based on indicator confluence and configured weights.
    *   Display current market data, indicator values, and signal breakdown.
    *   Manage any open positions (check for SL/TP hits).
    *   If a strong trading signal is present and trade management is enabled:
        *   Calculate entry price, Stop Loss, and Take Profit levels using ATR.
        *   Attempt to open a new position via the `PositionManager`.
    *   Log performance summary.
    *   Wait for the configured `loop_delay` before the next iteration.

3.  **Error Handling**:
    *   Includes `try...except` blocks to catch and log unhandled exceptions, preventing the bot from crashing.
    *   API request retries are handled by the `requests.Session` and `urllib3.util.retry.Retry` configuration.

## Key Configuration Options

*   `symbol`: The trading pair (e.g., "BTCUSDT").
*   `interval`: The primary candlestick interval (e.g., "15" for 15 minutes).
*   `loop_delay`: Time in seconds to wait between analysis cycles.
*   `trade_management`: Settings for order sizing, risk management, SL/TP multiples, etc.
*   `mtf_analysis`: Configuration for analyzing higher timeframes.
*   `indicator_settings`: Periods and parameters for all supported technical indicators.
*   `indicators`: Boolean flags to enable/disable specific indicators.
*   `weight_sets`: Defines how much each indicator/condition contributes to the final trading signal score.
*   `signal_score_threshold`: The minimum score required to generate a BUY or SELL signal.

## Customization

*   **Strategies**: Create new entries in `weight_sets` in `config.json` to define different trading strategies by adjusting indicator weights.
*   **Indicators**: Enable/disable indicators in the `indicators` section and tune their parameters in `indicator_settings`.
*   **Risk Management**: Adjust `trade_management` parameters like `risk_per_trade_percent`, `stop_loss_atr_multiple`, and `take_profit_atr_multiple`.
*   **Notifications**: Extend the `AlertSystem` class to integrate with external notification platforms.
*   **ML Integration**: The `ml_enhancement` section in the config (currently disabled) can be further developed to integrate a trained machine learning model for predictive signals.

This bot provides a robust framework for automated trading, offering flexibility and a wide range of analytical tools.
