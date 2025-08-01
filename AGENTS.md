# AGENTS.md: Guide for AI Software Engineers

This document provides instructions and guidelines for AI agents working on the Pyrmethus's Ultra Scalper Bot (PSG) codebase.

## 1. Project Overview

This is an advanced, asynchronous cryptocurrency trading bot designed for scalping on the Bybit derivatives exchange. It is built with Python and `asyncio` for high performance and real-time data processing.

The bot's architecture is modular, allowing for the dynamic selection and loading of different trading strategies. The core logic handles API interaction, WebSocket connections, position management, and order execution, while the strategy modules are responsible for generating trading signals.

## 2. Key Files & Directories

-   **`PSG.py`**: The main entry point of the application. It contains the core `asyncio` event loop, WebSocket handlers, and the main trading logic that orchestrates all other components.
-   **`config.py`**: The central configuration file. This is where you set trading parameters, API endpoints, risk management rules, and, most importantly, select the active trading strategy via the `STRATEGY_NAME` variable.
-   **`.env` (not in repo)**: Used for storing sensitive API keys (`BYBIT_API_KEY`, `BYBIT_API_SECRET`). It is loaded by the application at runtime.
-   **`bybit_api.py`**: A dedicated module for all interactions with the Bybit REST and WebSocket APIs.
-   **`indicators.py`**: Contains functions for calculating various technical indicators (e.g., StochRSI, ATR, SMA).
-   **`strategies/`**: This directory contains all the trading strategy implementations.
    -   **`strategy_template.py`**: The base class and interface for all strategies. New strategies **must** inherit from `StrategyTemplate` and implement its methods.
    -   **`stochrsi_fib_ob_strategy.py`**: An example of a complex, fully implemented strategy. Use this as a reference.
-   **`tests/`**: Contains unit tests for the project. The tests are written using the `pytest` framework.
-   **`bot_logger.py`**: Configures the logging for the application.
-   **`trade_metrics.py`**: A class for tracking and calculating trade performance statistics.
-   **`utils.py`**: Contains helper and utility functions used across the application.

## 3. Development Workflow

### How to Add a New Strategy

1.  **Create a New Strategy File**: In the `strategies/` directory, create a new Python file (e.g., `my_new_strategy.py`). The filename should be the lowercase version of your strategy's class name.
2.  **Implement the Strategy Class**:
    -   Inside your new file, create a class that inherits from `StrategyTemplate` (e.g., `class MyNewStrategy(StrategyTemplate):`).
    -   Implement the two required methods:
        -   `generate_signals(...)`: This method should contain your logic for generating *entry* signals (BUY or SELL). It must return a list of signal tuples.
        -   `generate_exit_signals(...)`: This method should contain your logic for generating *exit* signals for an existing position. It must also return a list of signal tuples.
    -   Refer to `strategies/strategy_template.py` for the exact method signatures and `strategies/stochrsi_fib_ob_strategy.py` for a complete example.
3.  **Add Configuration**: Open `config.py` and add any new configuration parameters your strategy requires.
4.  **Activate the Strategy**: In `config.py`, change the `STRATEGY_NAME` variable to the class name of your new strategy (e.g., `STRATEGY_NAME = "MyNewStrategy"`).

### How to Add a New Indicator

1.  **Add the Indicator Function**: Open `indicators.py` and add a new function for your technical indicator.
2.  **Input/Output**: The function should typically take a pandas DataFrame of kline data as input and return the calculated indicator data, usually as a new pandas Series or by adding a new column to the input DataFrame.
3.  **Integration**: Call your new indicator function from within the strategy that needs it, or from the main bot loop in `PSG.py` if it's a globally used indicator.

### How to Run Tests

The project uses `pytest`. To run the test suite:

1.  Make sure you have `pytest` installed (`pip install pytest`).
2.  From the root directory of the repository, run the following command:
    ```bash
    pytest
    ```
3.  When adding new functionality, especially to utility files like `utils.py` or `indicators.py`, you **must** add corresponding unit tests in the `tests/` directory.

## 4. Configuration

-   **Trading Logic**: All strategy parameters, symbol, interval, and risk management settings are in `config.py`. This is the primary file to modify for tuning the bot's behavior.
-   **API Keys**: **NEVER** hardcode API keys in `config.py`. Create a `.env` file in the root directory and add your keys there:
    ```
    BYBIT_API_KEY="YOUR_API_KEY"
    BYBIT_API_SECRET="YOUR_API_SECRET"
    ```

## 5. Coding Conventions

-   **Asynchronous Code**: The entire application is built on `asyncio`. All I/O operations (API calls, WebSocket messages) must be `async`.
-   **Financial Precision**: All calculations involving price, quantity, or other financial data **must** use Python's `Decimal` type to avoid floating-point inaccuracies. Do not use standard floats for these calculations.
-   **Logging**: The bot uses Python's `logging` module. Use the provided logger instances (`self.logger` in classes) to log events, signals, and errors.
-   **Modularity**: Keep concerns separated. API logic belongs in `bybit_api.py`, indicator calculations in `indicators.py`, and strategy logic in the `strategies/` directory.
-   **Error Handling**: Wrap API calls and other potentially failing operations in `try...except` blocks to ensure the bot remains resilient. Use the provided logging functions to report exceptions.
