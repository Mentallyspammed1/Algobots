# Algobots HTML Project

This project contains a collection of Python-based algorithmic trading components and a FastAPI backend for the Bybit exchange, along with associated HTML documentation and test files.

## Features

- **Trading Bot Core (`backbone.py`, `bb.py`):** Handles Bybit API interactions, order management, position tracking, and account balance retrieval.
- **Technical Indicators (`indicators.py`, `indicators_api.py`):** Provides functions for calculating various technical analysis indicators (EMA, RSI, Supertrend).
- **Backtesting Framework (`backtester.py`):** Allows for simulating trading strategies on historical data.
- **FastAPI Backend (`backend_app.py`):** Exposes API endpoints for fetching mock kline data and calculating indicators, enabling web-based interaction.
- **API Key Verification (`verify_keys.py`):** A utility to check the validity of Bybit API credentials.
- **Comprehensive Testing:** Unit and integration tests for core components and the new backend.
- **HTML Documentation:** Various HTML files providing conceptual overviews and setup guides for different bot versions and indicators.

## Installation

1.  **Clone the repository (if applicable):**
    ```bash
    # Assuming you have git installed
    git clone <repository_url>
    cd Algobots/html
    ```

2.  **Install Python Dependencies:**
    It's highly recommended to use a Python virtual environment.
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: .\venv\Scripts\activate
    pip install -r requirements.txt
    ```

3.  **Set up Environment Variables:**
    Create a `.env` file in the project root (`/data/data/com.termux/files/home/Algobots/html/`) and add your Bybit API credentials:
    ```
    BYBIT_API_KEY="YOUR_API_KEY"
    BYBIT_API_SECRET="YOUR_API_SECRET"
    ```
    **Important:** Replace `"YOUR_API_KEY"` and `"YOUR_API_SECRET"` with your actual Bybit API credentials. Keep this file secure and do not commit it to version control.

## Usage

### Running the FastAPI Backend

To start the backend server:

```bash
# Ensure your virtual environment is activated
uvicorn backend_app:app --host 0.0.0.0 --port 8000 --reload
```

The server will typically run on `http://0.0.0.0:8000`. You can access the API documentation at `http://0.0.0.0:8000/docs`.

**Endpoints:**
- `GET /klines`: Fetches mock historical kline data.
- `POST /indicators`: Calculates technical indicators on provided kline data.

### Running the Trading Bot (Conceptual)

The main trading bot logic is typically orchestrated by `bb.py`. You would run it as a standard Python script:

```bash
# Ensure your virtual environment is activated
python bb.py
```

*(Note: The exact execution flow and configuration for `bb.py` may vary based on its internal implementation and strategy.)*

### Running API Key Verification

To verify your Bybit API keys:

```bash
# Ensure your virtual environment is activated
python verify_keys.py
```

## Project Structure

```
Algobots/html/
├── .env                     # Environment variables (API keys)
├── requirements.txt         # Python dependencies
├── backbone.py              # Core Bybit API interaction logic
├── backtester.py            # Trading strategy backtesting framework
├── bb.py                    # Main trading bot orchestration script
├── indicators.py            # Original technical indicators module
├── indicators_api.py        # New technical indicators module for backend
├── backend_app.py           # FastAPI backend application
├── verify_keys.py           # Script to verify API keys
├── merged_html_output.html  # Merged content of all HTML documentation files
├── tests/                   # Directory for test files
│   ├── test_backbone.py
│   ├── test_backtester.py
│   ├── test_indicators.py
│   ├── test_indicators_api.py # Tests for indicators_api.py
│   └── test_backend_app.py    # Tests for backend_app.py
└── *.html, *.md, *.sh       # Various HTML documentation, Markdown notes, and shell scripts
```

## Testing

To run all tests for the project:

```bash
# Ensure your virtual environment is activated
python -m pytest tests/
```

To run tests for specific modules (e.g., the new backend and indicators):

```bash
python -m pytest tests/test_indicators_api.py tests/test_backend_app.py
```

## Contributing

Contributions are welcome! Please ensure your code adheres to the existing style, includes appropriate tests, and updates documentation as needed.

## License

[Specify your license here, e.g., MIT License]