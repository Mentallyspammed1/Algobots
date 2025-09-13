# Pybit JavaScript Scalper Bot

This project implements a sophisticated scalping bot for the Bybit exchange, built with Node.js and leveraging the Bybit V5 API. It is designed for automated cryptocurrency trading, focusing on high-frequency, short-term price movements.

## Features

- **Multiple Trading Strategies**: Supports various technical analysis-driven strategies, including Ehlers Supertrend and Chandelier Exit.
- **Real-time Data**: Utilizes Bybit WebSockets for live market data (kline updates).
- **Precision Trading**: Employs `Decimal.js` for accurate financial calculations, mitigating floating-point errors.
- **Robust Order Management**: Handles order placement, cancellation, amendment, and position closing.
- **Risk Management**: Includes features like emergency stop, position reconciliation, and dynamic stop-loss/take-profit.
- **State Persistence**: Uses SQLite to store and manage trade and position data, allowing for bot restarts.
- **Configurable**: Centralized configuration (`unified_config.js`) for easy customization of API settings, trading parameters, and strategy specifics.
- **Logging**: Comprehensive, color-coded logging for monitoring bot operations and debugging.
- **Dry Run Mode**: Safely test strategies without executing real trades.

## Getting Started

### Prerequisites

- Node.js (v16 or higher recommended)
- npm (Node Package Manager)
- A Bybit account (Unified Trading Account recommended for full functionality)

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd pybit/javabot
    ```
2.  **Install dependencies:**
    ```bash
    npm install
    ```
3.  **Configure API Keys:**
    Create a `.env` file in the `pybit/javabot` directory with your Bybit API key and secret:
    ```
    BYBIT_API_KEY=YOUR_API_KEY
    BYBIT_API_SECRET=YOUR_API_SECRET
    ```
    *Ensure these keys have appropriate permissions for trading and account access on Bybit.*

4.  **Review Configuration:**
    Adjust trading parameters and strategy settings in `config/unified_config.js` to match your preferences and risk tolerance. Pay close attention to `dryRun` and `testnet` settings.

### Running the Bot

To start the bot, execute:

```bash
npm start
```

The bot will begin connecting to Bybit, fetching market data, and executing trades based on the configured strategy. Monitor the console output for real-time logs.

## Testing

Unit tests are available to verify core functionalities and indicator calculations.

To run tests:

```bash
npm test
```

## Project Structure

```
pybit/javabot/
├── clients/                # Bybit API interaction (REST and WebSocket)
├── config/                 # Centralized configuration
├── core/                   # Main bot logic and runner
├── indicators/             # Technical indicator calculations
├── models/                 # Data models (Trade, Position)
├── persistence/            # SQLite database management
├── strategies/             # Trading strategy implementations
├── utils/                  # Utility functions (logging, math helpers)
├── __tests__/              # Unit tests
├── .env                    # Environment variables (API keys)
├── main.js                 # Bot entry point
├── package.json            # Project dependencies and scripts
├── package-lock.json       # Dependency lock file
├── README.md               # Project overview
├── TODO.txt                # Development tasks and improvements
└── ...
```

## Contributing

Contributions are welcome! Please refer to the `TODO.txt` for planned improvements and `GEMINI.md` for detailed architectural insights.

## License

This project is licensed under the ISC License.