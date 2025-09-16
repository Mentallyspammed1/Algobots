# Algobots/marketmaker Project Overview

This project, `Algobots/marketmaker`, is a comprehensive suite of Python tools designed for developing, backtesting, optimizing, and running a market-making bot on the Bybit exchange. It leverages the Pybit library for interacting with Bybit's V5 API, utilizing both REST and WebSocket protocols for real-time market data, order management, and position tracking.

## Core Components

### 1. Market Maker Core (`market_maker.py`)
This is the heart of the market-making bot. It encapsulates the core logic for quoting, order management, and position protection.

- **BybitRest**: Handles all HTTP REST API interactions, including fetching instrument information, placing/amending/canceling batch orders, and setting trailing stops or stop-loss orders.
- **PublicWS**: Manages public WebSocket connections to receive real-time order book data (depth 50) and calculate mid-price and microprice.
- **PrivateWS**: Manages private WebSocket connections for real-time updates on positions, orders, and executions.
- **Quoter**: Computes optimal bid and ask prices based on configured spreads and current market conditions. It uses batch endpoints to efficiently place and manage limit orders (PostOnly by default).
- **Protection**: Implements risk management strategies, including trailing stop-loss and break-even stop-loss, which activate based on position PnL.
- **MarketMaker (formerly App)**: The main class orchestrating the market-making operations, connecting all sub-components and running the main loop for quoting and protection.

### 2. Configuration (`config.py`)
This file defines all configurable parameters for the bot, loaded from environment variables (via `.env`) and set as dataclass attributes. It includes:

- **API Settings**: `API_KEY`, `API_SECRET`, `TESTNET`.
- **Trading Parameters**: `SYMBOL`, `CATEGORY`.
- **Market Making Parameters**: `BASE_SPREAD_BPS`, `MIN_SPREAD_TICKS`, `QUOTE_SIZE`, `REPLACE_THRESHOLD_TICKS`, `REFRESH_MS`, `POST_ONLY`.
- **Inventory/Risk**: `MAX_POSITION`, `MAX_NOTIONAL`.
- **Protection Mode**: `PROTECT_MODE` ("trailing", "breakeven", "off"), `TRAILING_DISTANCE`, `TRAILING_ACTIVATE_PROFIT_BPS`, `BE_TRIGGER_BPS`, `BE_OFFSET_TICKS`.
- **Logging**: `LOG_EVERY_SECS`, `WS_PING_SECS`.
- **Backtester Settings**: `INITIAL_CAPITAL`, `START_DATE`, `END_DATE`, `INTERVAL`, `MAKER_FEE`, `TAKER_FEE`, `SLIPPAGE`, `USE_ORDERBOOK`, `ORDERBOOK_DEPTH`, `USE_WEBSOCKET`.

### 3. Main Execution (`main.py`)
This is the primary entry point for running the bot. It determines whether to run the market maker in live mode (using WebSockets) or in backtest mode.

- **Live Mode**: Instantiates `MarketMaker` and calls its `run()` method, which handles real-time operations.
- **Backtest Mode**: Configures `BacktestParams` and uses `MarketMakerBacktester` to simulate the bot's performance over historical data.

## Backtesting Framework (`backtest.py`)
This module provides a robust framework for backtesting the `MarketMaker` bot against historical kline data from Bybit.

- **BacktestParams**: Dataclass defining parameters for a backtest run (symbol, interval, date range, fees, fill model).
- **BybitHistoricalData**: Fetches historical klines from Bybit's V5 API, handling pagination.
- **FillEngine**: Simulates order fills within historical candles, considering intra-candle price paths and volume capacity. It also emulates SL/TP based on `Config` parameters.
- **MarketMakerBacktester**: Orchestrates the backtesting process, running the `MarketMaker` logic step-by-step over historical data and calculating performance metrics like net PnL, max drawdown, and Sharpe ratio.

## Optimization Tools

### 1. Optuna-based Optimizers (`bot_optimizer.py`, `profit_optimizer.py`)
These modules use the `optuna` library for hyperparameter optimization of the market maker bot.

- **`bot_optimizer.py`**: A simpler Optuna integration that suggests parameters for spreads, order management, risk, and volatility, then runs backtests to optimize for net PnL.
- **`profit_optimizer.py`**: A more advanced Optuna optimizer. It pre-fetches historical data once, allows tuning of a wider range of market maker parameters (including detailed spread, order ladder, inventory, volatility, and risk settings), and optimizes based on net PnL (with risk penalty) or Sharpe ratio. It supports parallel execution and saves detailed trial results and equity curves.

### 2. Grid Search Optimizer (`optimizer.py`)
This module provides a generic grid search optimization approach.

- **Optimizer**: Iterates through predefined combinations of parameters, runs a backtest for each, and identifies the best-performing sets based on PnL and return percentage.

## Live Data & Simulation

### 1. Live Data Generator (`live_data_generator.py`)
This module provides a way to stream real-time market data.

- **LiveDataGenerator**: Uses Pybit WebSockets to subscribe to order book and trade streams, putting incoming messages into a queue for consumption.

### 2. Live Trader (`live_trader.py`)
This file appears to be an entry point for a live trading *simulation*.

- It uses `LiveDataGenerator` to feed real-time data into a `LiveSimulator` (which is not defined in the provided files, suggesting it might be a separate or missing component).

## Utilities & Statistics

### 1. Basic Profit Optimizer (`basic_profit_optimizer.py`)
This file contains a generic linear programming example using `pulp` for profit optimization. It's a standalone example and not directly integrated with the market maker bot's parameters.

### 2. Statistics (`statistics.py`)
This module provides functionality to calculate and display various trading statistics for the market maker bot, such as runtime, total trades, current position, PnL (realized and unrealized), average spread, and volatility.

## Dependencies

Key Python libraries used in this project include:
- `pybit`: For Bybit API interaction (REST and WebSockets).
- `pandas`, `numpy`: For data manipulation and numerical operations, especially in backtesting.
- `optuna`: For hyperparameter optimization.
- `python-dotenv`: For loading environment variables.
- `pulp`: For linear programming (in `basic_profit_optimizer.py`).
- `asyncio`: For asynchronous operations, particularly with WebSockets.

## Setup & Usage

1.  **Clone the repository**.
2.  **Install dependencies**: `pip install -r requirements.txt` (assuming `requirements.txt` lists all necessary packages).
3.  **Configure**: Create a `.env` file in the project root with your `BYBIT_API_KEY`, `BYBIT_API_SECRET`, and `BYBIT_TESTNET` (e.g., `BYBIT_TESTNET=True` for testnet).
4.  **Run Live Bot**: Execute `python main.py` with `USE_WEBSOCKET = True` in `config.py`.
5.  **Run Backtest**: Execute `python main.py` with `USE_WEBSOCKET = False` in `config.py` and configure `START_DATE`, `END_DATE`, etc., in `config.py`.
6.  **Optimize Parameters**: Run `python bot_optimizer.py` or `python profit_optimizer.py` (configure arguments as needed).

## Future Enhancements/Considerations

- **Complete `LiveSimulator`**: Implement the `LiveSimulator` for a full live trading simulation environment.
- **Advanced Risk Management**: Implement more sophisticated risk controls (e.g., daily loss limits, circuit breakers).
- **Layered Quoting**: Enhance the `Quoter` to support multiple price levels for bids and asks, as hinted in `config.py`'s `ORDER_LEVELS`.
- **Dynamic Parameter Adjustment**: Implement logic to dynamically adjust market-making parameters (spreads, quantities) based on real-time market volatility or inventory skew.
- **Logging & Monitoring**: Improve logging detail and add external monitoring/alerting capabilities.
- **Error Handling**: Enhance error handling and reconnection logic for robustness.

This `GEMINI.md` provides a comprehensive overview of the `Algobots/marketmaker` project, its components, and functionalities. It serves as a guide for understanding, using, and further developing the market-making bot and its associated tools.
