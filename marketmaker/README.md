# Algobots/marketmaker - Bybit Market Making Bot

This project provides a comprehensive suite of Python tools for developing, backtesting, optimizing, and running a market-making bot on the Bybit exchange. It leverages the Pybit library for interacting with Bybit's V5 API, utilizing both REST and WebSocket protocols for real-time market data, order management, and position tracking.

## Features

-   **Core Market Maker Logic**: Implements quoting, order management, and position protection strategies.
-   **Real-time Data**: Connects to Bybit WebSockets for live order book data and execution updates.
-   **Backtesting Framework**: Simulate bot performance against historical kline data with a configurable fill engine.
-   **Hyperparameter Optimization**: Integrates `Optuna` and grid search for finding optimal trading parameters.
-   **Configurable**: Centralized configuration management using environment variables and Python dataclasses.
-   **Risk Management**: Includes features like trailing stop-loss and break-even stop-loss.
-   **Modular Design**: Components are designed for reusability and testability.

## Getting Started

### Prerequisites

-   Python 3.8+
-   `pip` (Python package installer)
-   A Bybit account (Unified Trading Account recommended)

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd Algobots/marketmaker
    ```
2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Configure API Keys:**
    Create a `.env` file in the `Algobots/marketmaker` directory with your Bybit API key and secret:
    ```
    BYBIT_API_KEY=YOUR_API_KEY
    BYBIT_API_SECRET=YOUR_API_SECRET
    BYBIT_TESTNET=True # Set to False for live trading
    ```
    *Ensure these keys have appropriate permissions for trading and account access on Bybit.*

4.  **Review Configuration:**
    Adjust trading parameters and strategy settings in `config.py` to match your preferences and risk tolerance.

### Running the Bot

To run the bot in live mode (using WebSockets):

```bash
python main.py # Ensure USE_WEBSOCKET is True in config.py
```

To run a backtest:

```bash
python main.py # Ensure USE_WEBSOCKET is False in config.py and configure START_DATE, END_DATE, etc.
```

### Optimization

To optimize parameters using Optuna:

```bash
python profit_optimizer.py # Or bot_optimizer.py
```

## Project Structure

```
Algobots/marketmaker/
├── clients/                # Bybit API interaction (REST and WebSocket)
├── core/                   # Core market maker components (Quoter, Protection)
├── strategies/             # Market making strategy implementations
├── backtesting/            # Backtesting framework (FillEngine, HistoricalData)
├── optimization/           # Hyperparameter optimization tools
├── tests/                  # Unit and integration tests
├── config.py               # Centralized configuration
├── main.py                 # Bot entry point
├── requirements.txt        # Python dependencies
├── README.md               # Project overview
├── TODO.txt                # Development tasks and improvements
├── GEMINI.md               # Detailed AI agent documentation
└── ...
```

## Contributing

Contributions are welcome! Please refer to the `TODO.txt` for planned improvements and `GEMINI.md` for detailed architectural insights.

## License

This project is licensed under the ISC License.
