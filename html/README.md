# Algobots HTML

A collection of Python-based algorithmic trading components designed for the Bybit exchange, featuring core bot logic, technical indicators, a backtesting framework, and a FastAPI backend for data and indicator serving. This project also includes comprehensive HTML documentation and test suites.

## 🚀 Features

*   **Core Trading Logic:** Interact with the Bybit V5 API for order placement, position management, and account balance queries.
*   **Technical Indicators:** Implementations for various technical analysis indicators (e.g., EMA, RSI, Supertrend).
*   **Backtesting Framework:** Simulate trading strategies on historical data to evaluate performance.
*   **FastAPI Backend:** A web API to serve mock kline data and calculate indicators on demand.
*   **Comprehensive Documentation:** HTML and Markdown files detailing bot versions, setup, and concepts.
*   **Robust Testing:** Unit and integration tests for critical components.

## 🏗️ Project Structure

```
.
├── backbone.py             # Bybit V5 API interaction layer
├── backend_app.py          # FastAPI application for data/indicators
├── backtester.py           # Backtesting framework
├── bb.py                   # Main trading bot orchestration script
├── indicators.py           # Original technical indicator calculations
├── indicators_api.py       # Technical indicators for FastAPI backend
├── requirements.txt        # Python dependencies
├── tests/                  # Unit and integration tests
├── .env                    # Environment variables (API keys)
└── *.html, *.md            # Documentation and notes
```

## 🛠️ Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd Algobots/html
    ```
2.  **Create a Python virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate # On Windows: `venv\Scripts\activate`
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## ⚙️ Configuration

Create a `.env` file in the project root with your Bybit API credentials:

```
BYBIT_API_KEY="YOUR_API_KEY"
BYBIT_API_SECRET="YOUR_API_SECRET"
```

**Important:** Ensure your Bybit account is a **Unified Trading Account (UTA)**, as the bot is designed to work with UTA.

## ▶️ Usage

### Running the Trading Bot (Example)

```bash
python bb.py
```
*(Note: This is a placeholder. Refer to `bb.py` for specific arguments or execution details.)*

### Running the Backtester

```bash
python backtester.py
```
*(Note: This is a placeholder. Refer to `backtester.py` for specific arguments or execution details.)*

### Running the FastAPI Backend

```bash
uvicorn backend_app:app --reload
```
The API will be available at `http://127.0.0.1:8000`.
*   **Endpoints:**
    *   `GET /klines`: Get mock historical kline data.
    *   `POST /indicators`: Calculate technical indicators.

## ✅ Testing

To run the project's tests:

```bash
pytest
```

## 🤝 Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## 📄 License

This project is licensed under the MIT License. See the `LICENSE` file for details.
