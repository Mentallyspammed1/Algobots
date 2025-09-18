
✦ Of course. Here is a detailed trace of the execution flow for
  wb.bak2.py.

  1. Initialization Phase

   1. Script Entry: The program starts when the if __name__ ==
      "__main__": block is executed, which immediately calls the
      main() function. This is the primary entry point of the
      application.

   2. Logger and Configuration Setup:
       * main() first calls setup_logger("wgwhalex_bot"). This
         function configures a central logging system with two
         handlers: one that prints to the console with colored
         output and another that saves logs to a rotating file
         (bot_logs/trading-bot/logs/wgwhalex_bot.log). A custom
         SensitiveFormatter is used to automatically redact the
         API_KEY and API_SECRET from all log messages for
         security.
       * Next, load_config(CONFIG_FILE, logger) is called to read
         the config.json file.
           * If the file does not exist, a default configuration
             is created and saved.
           * If the file exists, it is loaded, and the
             _ensure_config_keys() helper function is called to
             recursively add any missing configuration keys from
             the default template. This ensures backward
             compatibility when new settings are added to the
             bot.

   3. Core Component Instantiation:
       * AlertSystem(logger): An object to handle sending
         critical notifications. In this version, it logs alerts
         to the console with distinct colors.
       * PositionManager(config, logger, symbol): An object
         responsible for all trade-related actions, including
         calculating order sizes, opening new positions, and
         managing stop-loss/take-profit levels for open trades.
       * PerformanceTracker(logger, config): An object that
         records every completed trade, calculates profit and
         loss (PnL), and tracks overall performance metrics like
         win rate.

   4. Configuration Validation: Before entering the main loop, the
      script validates that the interval and higher_timeframes
      specified in the configuration are valid according to the
      Bybit API's expected formats. If an invalid interval is
      found, the program logs an error and exits to prevent API
      errors.

  2. Main Trading Loop

  The script now enters an infinite while True: loop, which
  constitutes the bot's main operational cycle.

   1. Fetch Market Data:
       * fetch_current_price(): Retrieves the latest market price
         for the configured trading symbol (e.g., "BTCUSDT").
       * fetch_klines(): Fetches the most recent 1000 k-line
         (candlestick) data points for the primary trading
         interval (e.g., "15" for 15-minute candles). This data
         is loaded into a pandas DataFrame.
       * fetch_orderbook(): If the orderbook_imbalance indicator
         is enabled in the config, this function is called to get
         a snapshot of the current order book.
       * Multi-Timeframe (MTF) Analysis: If mtf_analysis is
         enabled, the bot loops through each higher_timeframes
         (e.g., "60", "240"), fetches the k-line data for each,
         and determines the trend ("UP", "DOWN", or "SIDEWAYS")
         using the indicators specified in trend_indicators
         (e.g., "ema", "ehlers_supertrend").

   2. Technical Analysis and Signal Generation:
       * TradingAnalyzer(df, config, logger, symbol): A new
         TradingAnalyzer object is instantiated with the primary
         k-line DataFrame.
       * _calculate_all_indicators(): This method is called from
         the TradingAnalyzer's constructor. It systematically
         calculates a wide array of technical indicators based on
         the settings in config.json. This includes SMAs, EMAs,
         RSI, MACD, Bollinger Bands, and the more advanced Ehlers
         SuperTrend, among others. The results are stored as new
         columns in the DataFrame.
       * generate_trading_signal(): This is the core
         decision-making function. It calculates a signal_score by
          evaluating the state of all calculated indicators
         against predefined rules and weights. For example, it
         checks for EMA crossovers, RSI overbought/oversold
         conditions, and MACD alignment. The MTF trends and order
         book imbalance also contribute to this score.
       * Based on the final signal_score and the
         signal_score_threshold from the config, a final signal
         of "BUY", "SELL", or "HOLD" is determined.

   3. Position and Performance Management:
       * position_manager.manage_positions(): This method is
         called to check if the current_price has crossed the
         stop-loss or take-profit level of any open positions. If
         a level is breached, the position is marked as "CLOSED",
         and the trade details are sent to the
         performance_tracker.
       * If a BUY or SELL signal is generated and meets the score
         threshold, position_manager.open_position() is called.
           * Inside open_position, the _calculate_order_size()
             method is used to determine the quantity to trade
             based on the account balance, risk per trade
             percentage, and the current ATR value (a measure of
             volatility).
           * A new position dictionary is created with entry
             price, stop-loss, take-profit, and other details,
             and it is added to the open_positions list.
       * performance_tracker.get_summary(): Retrieves the latest
         performance metrics.

   4. Logging and Display:
       * display_indicator_values_and_price(): This function logs
         a clean, formatted table of the current price and the
         values of all calculated indicators, providing a snapshot
          of the market state.
       * The bot then logs the final trading signal, the status
         of any open positions, and the overall performance
         summary.

   5. Loop Delay: The script calls time.sleep(config["loop_delay"])
       to pause for the configured number of seconds before the
      next loop iteration begins.

  Visualization of Execution Flow

  Here is a Mermaid flowchart that illustrates the behavior of the
  main loop:

   flowchart TD
       subgraph Initialization
           direction LR
           Init1[Start main()]
           Init2[Setup Logger & Config]
           Init3[Instantiate Managers]
           Init1 --> Init2 --> Init3
       end

       subgraph "Main Trading Loop"
           direction TB
           A[Start Loop Iteration] --> B{Fetch Market
   Data};
           B --> C{Perform Technical Analysis};
           C --> D{Generate Trading Signal};
           D --> E{Manage Existing Positions};
           E --> F{Is there a new strong signal?};
           F -- Yes --> G[Open New Position];
           F -- No --> H;
           G --> H[Display Info & Log Results];
           H --> I[Wait for Loop Delay];
           I --> A;
       end

       subgraph "Data Fetching"
           B1[Fetch Price]
           B2[Fetch Primary Klines]
           B3[Fetch Orderbook]
           B4[Fetch MTF Klines & Trends]
       end

       subgraph "Technical Analysis"
           C1[Instantiate TradingAnalyzer]
           C2[Calculate All Indicators (SMA, EMA, RSI,
   Ehlers SuperTrend, etc.)]
           C1 --> C2
       end

       subgraph "Signal Generation"
           D1[Calculate Weighted Signal Score]
           D2[Compare Score to Threshold]
       end

       Init3 --> A
       B --> B1 & B2 & B3 & B4
       C --> D
       D --> D1 --> D2
