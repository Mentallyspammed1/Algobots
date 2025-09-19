# Project Root Context: Algobots HTML

This `GEMINI.md` file provides context for the Gemini agent regarding the `Algobots/html` project directory. It summarizes the project's purpose, structure, and key components, including recent additions.

---

## 📜 Table of Contents

1.  [**Project Overview**](#-project-overview)
2.  [**Key Components & Architecture**](#-key-components--architecture)
3.  [**Bybit API & Trading Knowledge**](#-bybit-api--trading-knowledge)
4.  [**Development & Tooling**](#-development--tooling)
5.  [**Secrets & Memories**](#-secrets--memories)

---

## 🚀 Project Overview

This project is a collection of Python-based algorithmic trading components designed for the Bybit exchange. It includes core bot logic, technical indicator implementations, a backtesting framework, and a newly added FastAPI backend for data and indicator serving. The directory also contains various HTML documentation files and test suites.

---

## 🏗️ Key Components & Architecture

### Core Trading Logic
-   `backbone.py`: Handles all direct Bybit V5 API interactions (order placement, position management, account balance).
-   `bb.py`: The main orchestration script for the trading bot.
-   `verify_keys.py`: A utility script to verify Bybit API credentials.

### Technical Indicators
-   `indicators.py`: Original module for technical indicator calculations.
-   `indicators_api.py` (NEW): A dedicated module for technical indicator calculations, specifically designed for use with the FastAPI backend. Includes `calculate_ema`, `calculate_rsi`, and `calculate_supertrend`.

### Backtesting
-   `backtester.py`: A framework for simulating trading strategies on historical data.

### FastAPI Backend (NEW)
-   `backend_app.py`: A FastAPI application that exposes:
    -   `GET /klines`: Serves mock historical kline data.
    -   `POST /indicators`: Calculates and returns technical indicators based on provided kline data, utilizing `indicators_api.py`.

### Documentation & Utilities
-   Various `.html` files: Provide conceptual overviews, setup guides, and specific bot version details.
-   `merged_html_output.html`: A consolidated file containing all HTML documentation.
-   `.md` files: Additional markdown notes and help.
-   `.sh` scripts: Shell utility scripts.

### Testing
-   `tests/`: Contains unit and integration tests for various modules, including `test_indicators_api.py` and `test_backend_app.py` for the new components.

---

## 📈 Bybit API & Trading Knowledge

This project heavily relies on the Bybit V5 API. Key aspects include:
-   **API Interaction:** Uses the `pybit` Python library for both REST and conceptual WebSocket interactions.
-   **Account Type:** Designed for Unified Trading Accounts (`accountType="UNIFIED"`).
-   **Order Types:** Supports various order types (Market, Limit) and parameters (stop-loss, take-profit, reduce-only).
-   **Data:** Processes historical kline data for indicator calculations and backtesting.

---

## 🛠️ Development & Tooling

-   **Python Environment:** Uses `venv` for isolated environments.
-   **Dependencies:** Managed via `requirements.txt` (includes `pandas`, `numpy`, `python-dotenv`, `pybit`, `ta`, `fastapi`, `uvicorn`, `pytest`, `httpx`).
-   **Testing:** `pytest` is used for running tests. Tests are located in the `tests/` directory.
-   **API Keys:** Loaded securely from `.env` file using `python-dotenv`.

---

## 💎 Secrets & Memories

-   The user's Bybit API Key and Secret are stored securely in environment variables and are not exposed in code or logs.
-   The agent has been provided with detailed context on Bybit V5 API functions and WebSocket capabilities in previous interactions.

---
