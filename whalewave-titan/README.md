
WhaleWave Titan
This project is an AI-powered trading engine and real-time monitor designed for the Bybit exchange. It leverages the Google Gemini API for advanced market analysis and a suite of technical indicators to generate trading signals. The system includes a paper trading simulation and a live dashboard for monitoring key metrics.

✨ Features

*   **AI-Powered Analysis:** Utilizes the Google Gemini API (gemini-2.5-flash-lite model) to analyze market data, incorporating multiple technical indicators and multi-timeframe analysis to generate trading signals with confidence scores.
*   **Comprehensive Technical Indicators:** Implements a wide array of technical indicators, including:
    *   **Smoothing:** ZLEMA (Zero Lag Exponential Moving Average)
    *   **Momentum:** RSI, Stochastic Oscillator (%K, %D), MFI, CCI
    *   **Trend:** MACD, ADX, SuperTrend, Chandelier Exit, Linear Regression
    *   **Volatility:** ATR, Bollinger Bands, Keltner Channels, Historical Volatility, Market Regime detection
    *   **Structure:** VWAP, Fair Value Gap (FVG), Order Book Walls, Fibonacci Pivots
*   **Signal Generation:** Divergence detection, WSS (Weighted Sentiment Score) calculation.
*   **Paper Trading Simulation:** Features a robust paper trading environment using Decimal.js for precise financial calculations, preventing floating-point errors. It includes configurable risk management parameters such as initial balance, risk per trade, maximum drawdown, and daily loss limits.
*   **Real-time Dashboard:** A live, interactive dashboard (served via Express.js and rendered in index.html) provides a visual overview of critical data:
    *   Current market price and symbol.
    *   WSS score and AI-generated action (BUY/SELL/HOLD) with confidence and reason.
    *   Account balance and daily PnL.
    *   Open position details (side, entry, SL, TP, PnL).
    *   Key indicator values (RSI, ADX, Stochastics, Chop, FVG, MTF Trend, Regime).
    *   Live system logs.
*   **Modular Architecture:** The codebase is structured into distinct modules (engine.js, indicators.js, config.json, server.js) for clarity, maintainability, and extensibility.
*   **Configuration Driven:** Key parameters are externalized in config.json and sensitive API keys are managed via a .env file.
*   **Robust Error Handling:** Includes retry mechanisms for API requests and comprehensive error handling for continuous operation.
*   **Neon Colorization:** Utilizes the chalk library for vibrant, neon-themed console output, enhancing the user experience.

🛠️ Technology Stack

*   **Runtime:** Node.js
*   **Core Libraries:**
    *   Express.js (for the dashboard server)
    *   Axios (for API requests)
    *   Chalk (for terminal styling)
    *   Decimal.js (for precise financial calculations)
    *   dotenv (for environment variable management)
    *   @google/generative-ai (for Gemini API integration)
    *   timers/promises (for async setTimeout)
*   **APIs:**
    *   Bybit V5 API (for market data)
    *   Google Gemini API (for AI analysis)

⚙️ Configuration

1.  **Environment Variables (.env)**
    Create a .env file in the project root to store sensitive API credentials. Never commit this file to version control.
    ```
    GEMINI_API_KEY=your_gemini_api_key_here
    PORT=3000 # Optional: Port for the dashboard server
    ```
2.  **Trading Parameters (config.json)**
    The config.json file centralizes all configurable parameters for the trading engine, including:
    *   Trading Symbol & Intervals: `symbol`, `interval`, `trend_interval`
    *   AI Settings: `gemini_model`, `min_confidence`
    *   Risk Management: `risk.max_drawdown`, `risk.daily_loss_limit`, `risk.max_positions`
    *   Paper Trading: `paper_trading.initial_balance`, `risk_percent`, `leverage_cap`, `fee`, `slippage`
    *   Indicators: Parameters for various technical indicators (RSI, MACD, Bollinger Bands, SuperTrend, etc.) and weights for the WSS (Weighted Sentiment Score) calculation.
    *   Orderbook & API: Settings for order book depth, wall thresholds, API timeouts, and retries.

▶️ Running the Bot

1.  **Install Dependencies:**
    ```bash
    npm install
    ```
2.  **Configure:**
    *   Create a `.env` file with your `GEMINI_API_KEY`.
    *   Adjust parameters in `config.json` as needed.
3.  **Start the Server and Engine:**
    ```bash
    npm start
    ```
    This command starts the Express server, which in turn launches the trading engine (`node engine.js`).
4.  **Access Dashboard:** Open your browser to `http://localhost:3000` (or the configured port).

🚀 Project Structure

```
1 whalewave-titan/
2 ├── .env                  # Environment variables (API keys)
3 ├── config.json           # Bot configuration parameters
4 ├── engine.js             # Core trading engine logic
5 ├── indicators.js         # Technical indicator calculations
6 ├── server.js             # Express server for the dashboard and engine management
7 ├── index.html            # Frontend dashboard
8 ├── package.json          # Node.js project metadata and dependencies
9 ├── package-lock.json     # Node.js dependency lock file
10 └── ...                   # Other project files (e.g., node_modules)
```

⚠️ Disclaimer

This project is for educational and informational purposes only. Cryptocurrency trading involves substantial risk of loss and is not suitable for all investors. Past performance is not indicative of future results. Use this software at your own risk. The developers are not responsible for any financial losses incurred.

🤝 Contributing

Contributions are welcome! Please refer to the project's contribution guidelines (if available) or submit a pull request.

📄 License

This project is likely licensed under the MIT License (based on common open-source practices, but check for an explicit LICENSE file).
