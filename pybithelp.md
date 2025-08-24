# The Grand Grimoire of Bybit Trading

This compendium serves as your complete guide to crafting powerful, modular trading bots on the Bybit V5 API using the `pybit` library.

## 📜 Table of Contents

1.  [Overview](#-overview)
2.  [Core Components](#-core-components)
3.  [Setup & Configuration](#-setup--configuration)
4.  [The Alchemist's Handbook: API Functions](#-the-alchemists-handbook-api-functions)
5.  [The Seer's Orb: Real-time Data with WebSockets](#-the-seers-orb-real-time-data-with-websockets)
6.  [Rune of Precision: Handling Instrument Rules](#-rune-of-precision-handling-instrument-rules)
7.  [Advanced Risk Management: Position Sizing](#-advanced-risk-management-position-sizing)
8.  [Crafting Your Strategy with Pandas TA](#-crafting-your-strategy-with-pandas-ta)
9.  [The Oracle's Simulacrum: Backtesting Your Strategy](#-the-oracles-simulacrum-backtesting-your-strategy)
10. [The Alchemist's Crucible: Strategy Optimization](#-the-alchemists-crucible-strategy-optimization)
11. [Running Your Incantation](#-running-your-incantation)
12. [Best Practices](#-best-practices)

## 📖 Overview
(Section remains the same)

## 📂 Core Components
(Section remains the same)

## ⚙️ Setup & Configuration

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```
Your `requirements.txt` should contain:
```
pybit
pandas
pandas-ta
python-dotenv
vectorbt
optuna
```

### 2. Configure API Keys & Parameters
(Section remains the same)

## 🔮 The Alchemist's Handbook: API Functions
(Section remains the same)

## 👁️ The Seer's Orb: Real-time Data with WebSockets
(Section remains the same)

## ✨ Rune of Precision: Handling Instrument Rules
(Section remains the same)

## 🛡️ Advanced Risk Management: Position Sizing
(Section remains the same)

## ⚔️ Crafting Your Strategy with Pandas TA
(Section remains the same)

## 🔮 The Oracle's Simulacrum: Backtesting Your Strategy
(Section remains the same)

## 🧪 The Alchemist's Crucible: Strategy Optimization

A strategy is defined by its parameters (e.g., RSI length, MA period). Finding the *optimal* parameters is the key to unlocking a strategy's full potential. We can automate this search using `optuna` in conjunction with `vectorbt`.

### 1. Add `optuna` to `requirements.txt`
Ensure `optuna` is installed.

### 2. Create an Optimization Script
Create a new file, for example `optimizer.py`. This script will define an "objective" function for `optuna` to maximize.

### 3. The Optimization Incantation

This script will test 100 different combinations of your strategy's parameters to find the one that yields the highest Sharpe Ratio.

```python
# optimizer.py
import pandas as pd
import vectorbt as vbt
import optuna
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta

# Import your strategy class and data fetching function
from strategies.my_strategy import MyStrategy 
from backtester import fetch_historical_data

# --- 1. Configuration ---
SYMBOL = "BTCUSDT"
TIMEFRAME = "60"
START_DATE = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
INITIAL_CAPITAL = 10000
COMMISSION_RATE = 0.00075

# --- 2. Global variable for data to avoid re-fetching ---
price_data = None

# --- 3. Define the Objective Function for Optuna ---
def objective(trial):
    global price_data
    
    # A. Define the search space for your strategy's parameters
    rsi_period = trial.suggest_int('rsi_period', 10, 30)
    rsi_oversold = trial.suggest_int('rsi_oversold', 20, 40)
    rsi_overbought = trial.suggest_int('rsi_overbought', 60, 80)
    ema_period = trial.suggest_int('ema_period', 100, 300)

    # B. Create a strategy instance with the suggested parameters
    #    (You may need to modify your Strategy class to accept params in __init__)
    
    # Let's assume MyStrategy is modified like this:
    # class MyStrategy(BaseStrategy):
    #     def __init__(self, rsi_period=14, ...):
    #         self.rsi_period = rsi_period
    #         ...
    
    temp_strategy = MyStrategy()
    temp_strategy.rsi_period = rsi_period
    temp_strategy.rsi_oversold = rsi_oversold
    temp_strategy.rsi_overbought = rsi_overbought
    temp_strategy.ema_period = ema_period

    # C. Generate signals using these new parameters
    signals_df = temp_strategy.generate_signals(price_data)
    entries = signals_df['signal'] == 'buy'
    exits = signals_df['signal'] == 'sell'
    
    # D. Run the backtest
    portfolio = vbt.Portfolio.from_signals(
        price_data['close'],
        entries=entries,
        exits=exits,
        init_cash=INITIAL_CAPITAL,
        fees=COMMISSION_RATE,
        freq=f"{TIMEFRAME}T"
    )
    
    # E. Return the metric to optimize (e.g., Sharpe Ratio)
    return portfolio.sharpe_ratio()

# --- 4. Run the Optimization ---
if __name__ == "__main__":
    print("Fetching historical data for optimization...")
    price_data = fetch_historical_data(SYMBOL, TIMEFRAME, START_DATE)

    # Create an Optuna study
    study = optuna.create_study(direction='maximize') # We want to maximize the Sharpe Ratio

    print("Starting optimization process...")
    study.optimize(objective, n_trials=100) # Run 100 different trials

    print("\n--- Optimization Finished ---")
    print(f"Best Sharpe Ratio: {study.best_value}")
    print("Best Parameters:")
    for key, value in study.best_params.items():
        print(f"  {key}: {value}")

```

### How It Works:
1.  **Objective Function**: This function is the core of the optimization. For each `trial`, `optuna` suggests new values for your strategy parameters (`rsi_period`, `ema_period`, etc.) from the ranges you define.
2.  **Backtest Trial**: The objective function runs a full `vectorbt` backtest using these temporary parameters.
3.  **Return Metric**: It returns a single performance metric (like Sharpe Ratio or Total Return %). `optuna`'s goal is to find the parameter combination that maximizes this value.
4.  **Study**: The `study` object manages the entire optimization process, intelligently choosing which parameters to try next based on the results of previous trials.

## 🚀 Running Your Incantation
(Section remains the same, but now the full workflow is `optimizer.py` -> `backtester.py` -> `main.py`)

## ✨ Best Practices
(New point added)
-   **Optimize Wisely**: After finding the best parameters with `optimizer.py`, hardcode them into your strategy file. Then, run `backtester.py` one last time to see the full performance report of the optimized strategy before deploying it live with `main.py`.

```
# .gitignore
.env
__pycache__/
logs/
```

```