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

```import os
import sys
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

# =====================================================================
# CONFIGURATION
# =====================================================================

@dataclass
class Config:
    """Bot configuration"""
    API_KEY: str = os.getenv('BYBIT_API_KEY', '')
    API_SECRET: str = os.getenv('BYBIT_API_SECRET', '')
    TESTNET: bool = os.getenv('BYBIT_TESTNET', 'true').lower() == 'true'
    SYMBOL: str = "BTCUSDT"
    CATEGORY: str = "linear"  # 'linear', 'spot', 'inverse', 'option'
    LEVERAGE: int = 5
    RISK_PER_TRADE: float = 0.02  # 2% risk per trade
    MAX_POSITION_SIZE: float = 10000
    MIN_POSITION_SIZE: float = 10
    TIMEFRAME: str = "15"  # Kline interval
    LOOKBACK_PERIODS: int = 200
    MAX_DAILY_LOSS: float = 0.05  # 5% max daily loss
    MAX_OPEN_POSITIONS: int = 3
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "trading_bot.log"

# =====================================================================
# LOGGING SETUP
# =====================================================================

def setup_logger(config: Config) -> logging.Logger:
    """Setup logging configuration"""
    logger = logging.getLogger('TradingBot')
    logger.setLevel(getattr(logging, config.LOG_LEVEL))
    
    # File handler
    fh = logging.FileHandler(config.LOG_FILE)
    fh.setLevel(logging.DEBUG)
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger

# =====================================================================
# PRECISION MANAGER
# =====================================================================

class PrecisionManager:
    """Manages decimal precision for trading operations"""
    
    def __init__(self, session, logger):
        self.session = session
        self.logger = logger
        self.instruments = {}
        self.load_instruments()
    
    def load_instruments(self):
        """Load instrument specifications from Bybit"""
        try:
            response = self.session.get_instruments_info(
                category=self.session.category,
                symbol=self.session.symbol
            )
            
            if response['retCode'] == 0:
                spec = response['result']['list'][0]
                self.instruments[self.session.symbol] = {
                    'price_precision': len(str(spec['priceFilter']['tickSize']).split('.')[1]),
                    'qty_precision': len(str(spec['lotSizeFilter']['qtyStep']).split('.')[1]),
                    'tick_size': Decimal(spec['priceFilter']['tickSize']),
                    'qty_step': Decimal(spec['lotSizeFilter']['qtyStep']),
                    'min_qty': Decimal(spec['lotSizeFilter']['minOrderQty']),
                    'max_qty': Decimal(spec['lotSizeFilter']['maxOrderQty']),
                    'min_notional': Decimal(spec['lotSizeFilter'].get('minNotionalValue', '5'))
                }
                self.logger.debug(f"Instrument specs loaded for {self.session.symbol}")
            else:
                self.logger.error(f"Failed to load instrument specs: {response['retMsg']}")
                
        except Exception as e:
            self.logger.error(f"Error loading instruments: {e}")
    
    def round_price(self, price: float) -> Decimal:
        """Round price to correct tick size"""
        specs = self.instruments.get(self.session.symbol)
        if not specs:
            return Decimal(str(price))
        
        tick_size = specs['tick_size']
        return Decimal(str(price)).quantize(Decimal('1.' + '0'*int(specs['price_precision']))
    
    def round_qty(self, qty: float) -> Decimal:
        """Round quantity to correct step size"""
        specs = self.instruments.get(self.session.symbol)
        if not specs:
            return Decimal(str(qty))
        
        qty_step = specs['qty_step']
        return Decimal(str(qty)).quantize(Decimal('1.' + '0'*int(specs['qty_precision']))

# =====================================================================
# ORDER SIZING CALCULATOR
# =====================================================================

class OrderSizingCalculator:
    """Calculates optimal order sizes based on risk management"""
    
    def __init__(self, precision_manager, logger):
        self.precision = precision_manager
        self.logger = logger
    
    def calculate_position_size(self, entry_price: float, stop_loss_price: float) -> Decimal:
        """Calculate position size based on risk management rules"""
        try:
            # Get account balance
            balance = self.precision.get_account_balance()
            if balance <= 0:
                return Decimal('0')
            
            # Calculate risk amount
            risk_amount = balance * Decimal(str(self.precision.config.RISK_PER_TRADE))
            
            # Calculate stop loss distance
            stop_loss_distance = abs(Decimal(str(entry_price)) - Decimal(str(stop_loss_price))) / Decimal(str(entry_price))
            
            if stop_loss_distance == 0:
                return Decimal('0')
            
            position_size = risk_amount / stop_loss_distance
            
            # Apply leverage
            position_size = position_size * Decimal(str(self.precision.config.LEVERAGE))
            
            # Apply limits
            specs = self.precision.instruments.get(self.precision.session.symbol)
            if specs:
                position_size = min(position_size, specs['max_qty'])
                position_size = max(position_size, specs['min_qty'])
            
            # Round to appropriate decimal places
            return self.precision.round_qty(float(position_size))
            
        except Exception as e:
            self.logger.error(f"Error calculating position size: {e}")
            return self.precision.round_qty(self.precision.config.MIN_POSITION_SIZE)

# =====================================================================
# TRAILING STOP MANAGER
# =====================================================================

class TrailingStopManager:
    """Manages trailing stop losses for profitable positions"""
    
    def __init__(self, session, precision_manager, logger):
        self.session = session
        self.precision = precision_manager
        self.logger = logger
        self.trailing_stops = {}
    
    def initialize_trailing_stop(self, symbol: str, position_side: str, 
                                entry_price: float, current_price: float, 
                                trail_percent: float = 0.01) -> Dict:
        """Initialize trailing stop for a position"""
        try:
            entry = Decimal(str(entry_price))
            current = Decimal(str(current_price))
            trail_pct = Decimal(str(trail_percent))
            
            # Calculate activation price
            if position_side == "Buy":
                activation_price = entry * (1 + trail_pct)
                is_activated = current >= activation_price
                highest_price = current if is_activated else entry
                stop_loss = highest_price * (1 - trail_pct)
            else:  # Sell/Short
                activation_price = entry * (1 - trail_pct)
                is_activated = current <= activation_price
                lowest_price = current if is_activated else entry
                stop_loss = lowest_price * (1 + trail_pct)
            
            trailing_stop = {
                'symbol': symbol,
                'side': position_side,
                'entry_price': entry,
                'activation_price': activation_price,
                'trail_percent': trail_pct,
                'is_activated': is_activated,
                'highest_price': highest_price if position_side == "Buy" else None,
                'lowest_price': lowest_price if position_side == "Sell" else None,
                'current_stop': self.precision.round_price(float(stop_loss)),
                'last_update': datetime.now()
            }
            
            self.trailing_stops[symbol] = trailing_stop
            self.logger.info(f"Trailing stop initialized for {symbol}")
            return trailing_stop
            
        except Exception as e:
            self.logger.error(f"Error initializing trailing stop: {e}")
            return {}
    
    def update_trailing_stop(self, symbol: str, current_price: float) -> bool:
        """Update trailing stop based on current price"""
        try:
            if symbol not in self.trailing_stops:
                return False
            
            ts = self.trailing_stops[symbol]
            current = Decimal(str(current_price))
            
            # Update trailing stop logic
            if ts['side'] == "Buy":
                # Check if trailing stop should be activated
                if not ts['is_activated'] and current >= ts['activation_price']:
                    ts['is_activated'] = True
                    ts['highest_price'] = current
                    new_stop = current * (1 - ts['trail_percent'])
                    ts['current_stop'] = self.precision.round_price(float(new_stop))
                    self.logger.info(f"Trailing stop activated for {symbol}")
                
                # Update highest price and stop loss if activated
                if ts['is_activated'] and current > ts['highest_price']:
                    ts['highest_price'] = current
                    new_stop = current * (1 - ts['trail_percent'])
                    ts['current_stop'] = self.precision.round_price(float(new_stop))
                    self.logger.info(f"Trailing stop updated for {symbol}: {ts['current_stop']}")
                    
            elif ts['side'] == "Sell":
                # Check if trailing stop should be activated
                if not ts['is_activated'] and current <= ts['activation_price']:
                    ts['is_activated'] = True
                    ts['lowest_price'] = current
                    new_stop = current * (1 + ts['trail_percent'])
                    ts['current_stop'] = self.precision.round_price(float(new_stop))
                    self.logger.info(f"Trailing stop activated for {symbol}")
                
                # Update lowest price and stop loss if activated
                if ts['is_activated'] and current < ts['lowest_price']:
                    ts['lowest_price'] = current
                    new_stop = current * (1 + ts['trail_percent'])
                    ts['current_stop'] = self.precision.round_price(float(new_stop))
                    self.logger.info(f"Trailing stop updated for {symbol}: {ts['current_stop']}")
            
            # Update last timestamp
            ts['last_update'] = datetime.now()
            self.trailing_stops[symbol] = ts
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating trailing stop: {e}")
            return False
    
    def update_stop_on_exchange(self, symbol: str, stop_price: float):
        """Update stop loss on Bybit exchange"""
        try:
            response = self.session.set_trading_stop(
                category=self.session.category,
                symbol=symbol,
                stopLoss=str(stop_price)
            )
            
            if response['retCode'] == 0:
                self.logger.info(f"Stop loss updated on exchange for {symbol}: {stop_price}")
                return True
            else:
                self.logger.error(f"Failed to update stop loss: {response['retMsg']}")
                return False
                
        except Exception as e:
            self.logger.error(f"Exception updating stop loss: {e}")
            return False

# =====================================================================
# PNL TRACKING SYSTEM
# =====================================================================

class PnLTracker:
    """Tracks trading performance and statistics"""
    
    def __init__(self, session, precision_manager, logger):
        self.session = session
        self.precision = precision_manager
        self.logger = logger
        self.trades = []
        self.open_trades = {}
        self.closed_trades = []
        self.account_balance = 0
        self.start_balance = 0
        self.daily_pnl = 0
        self.position_history = []
    
    def add_trade(self, trade: dict):
        """Add a new trade to tracking"""
        self.trades.append(trade)
        if trade['status'] == 'OPEN':
            self.open_trades[trade['trade_id']] = trade
        else:
            self.closed_trades.append(trade)
    
    def get_account_balance(self) -> float:
        """Get current account balance"""
        try:
            response = self.session.get_wallet_balance(
                accountType="UNIFIED" if self.session.category != "spot" else "SPOT"
            )
            
            if response['retCode'] == 0:
                coins = response['result']['list'][0]['coin']
                for coin in coins:
                    if coin['coin'] == 'USDT':
                        balance = float(coin['walletBalance'])
                        self.account_balance = balance
                        return balance
                        
            self.logger.error(f"Failed to get balance: {response.get('retMsg', 'Unknown error')}")
            return 0
            
        except Exception as e:
            self.logger.error(f"Error getting balance: {e}")
            return 0
    
    def calculate_metrics(self) -> Dict:
        """Calculate comprehensive trading metrics"""
        if not self.closed_trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'total_pnl': 0,
                'gross_profit': 0,
                'gross_loss': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'largest_win': 0,
                'largest_loss': 0,
                'profit_factor': 0,
                'expectancy': 0,
                'max_drawdown': {'value': 0, 'percentage': 0},
                'sharpe_ratio': 0,
                'calmar_ratio': 0,
                'win_rate': 0,
                'avg_hold_time_hours': 0,
                'consecutive_wins': 0,
                'consecutive_losses': 0
            }
        
        # Basic metrics
        total_trades = len(self.closed_trades)
        winning_trades = [t for t in self.closed_trades if t['realized_pnl'] > 0]
        losing_trades = [t for t in self.closed_trades if t['realized_pnl'] < 0]
        total_pnl = sum(t['realized_pnl'] for t in self.closed_trades)
        gross_profit = sum(t['realized_pnl'] for t in winning_trades)
        gross_loss = sum(t['realized_pnl'] for t in losing_trades)
        avg_win = gross_profit / len(winning_trades) if winning_trades else 0
        avg_loss = abs(gross_loss / len(losing_trades)) if losing_trades else 0
        largest_win = max(t['realized_pnl'] for t in winning_trades) if winning_trades else 0
        largest_loss = min(t['realized_pnl'] for t in losing_trades) if losing_trades else 0
        
        # Risk metrics
        profit_factor = gross_profit / abs(gross_loss) if gross_loss != 0 else 0
        
        # Expectancy
        expectancy = (len(winning_trades) / total_trades * avg_win) - \
                     ((total_trades - len(winning_trades)) / total_trades * abs(avg_loss)) \
                     if total_trades > 0 else 0
        
        # Drawdown calculation
        equity_curve = [t['realized_pnl'] for t in self.closed_trades]
        max_drawdown = self._calculate_max_drawdown(equity_curve)
        
        # Sharpe ratio (simplified)
        returns = [t['pnl_percentage'] for t in self.closed_trades]
        sharpe_ratio = self._calculate_sharpe_ratio(returns) if returns else 0
        
        # Calmar ratio
        calmar_ratio = sharpe_ratio / abs(max_drawdown['value']) if max_drawdown['value'] != 0 else 0
        
        # Win rate
        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
        
        # Hold time
        hold_times = [t['hold_time'].total_seconds() / 3600 for t in self.closed_trades if t['hold_time']]
        avg_hold_time = np.mean(hold_times) if hold_times else 0
        
        # Consecutive wins/losses
        consecutive_wins = self._max_consecutive_wins()
        consecutive_losses = self._max_consecutive_losses()
        
        return {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'total_pnl': total_pnl,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'largest_win': largest_win,
            'largest_loss': largest_loss,
            'profit_factor': profit_factor,
            'expectancy': expectancy,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'calmar_ratio': calmar_ratio,
            'win_rate': win_rate,
            'avg_hold_time_hours': avg_hold_time,
            'consecutive_wins': consecutive_wins,
            'consecutive_losses': consecutive_losses
        }
    
    def _calculate_max_drawdown(self, equity_curve: List[float]) -> Dict:
        """Calculate maximum drawdown from equity curve"""
        if not equity_curve:
            return {'value': 0, 'percentage': 0}
        
        max_value = max(equity_curve)
        min_value = min(equity_curve)
        
        drawdown_value = max_value - min_value
        drawdown_percentage = (drawdown_value / max_value) * 100
        
        return {
            'value': drawdown_value,
            'percentage': drawdown_percentage
        }
    
    def _calculate_sharpe_ratio(self, returns: List[float]) -> float:
        """Calculate Sharpe ratio from returns"""
        if not returns or len(returns) < 2:
            return 0
        
        returns_array = np.array(returns)
        mean_return = np.mean(returns_array)
        std_dev = np.std(returns_array)
        
        if std_dev == 0:
            return 0
        
        # Assuming 252 trading days per year
        sharpe = (mean_return / std_dev) * np.sqrt(252)
        return sharpe
    
    def _max_consecutive_wins(self) -> int:
        """Find maximum consecutive winning trades"""
        if not self.closed_trades:
            return 0
        
        wins = [t['realized_pnl'] > 0 for t in self.closed_trades]
        max_streak = 0
        current_streak = 0
        
        for win in wins:
            if win:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
                
        return max_streak
    
    def _max_consecutive_losses(self) -> int:
        """Find maximum consecutive losing trades"""
        if not self.closed_trades:
            return 0
        
        losses = [t['realized_pnl'] < 0 for t in self.closed_trades]
        max_streak = 0
        current_streak = 0
        
        for loss in losses:
            if loss:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
                
        return max_streak
    
    def get_position_summary(self) -> List[Dict]:
        """Get summary of all positions"""
        positions = []
        
        for symbol, position in self.positions.items():
            # Calculate position metrics
            pnl_percentage = (position['unrealized_pnl'] / 
                             (position['size'] * position['mark_price']) * 100)
            
            positions.append({
                'symbol': position['symbol'],
                'side': position['side'],
                'size': float(position['size']),
                'avg_price': float(position['avgPrice']),
                'mark_price': float(position['markPrice']),
                'unrealized_pnl': float(position['unrealized_pnl']),
                'pnl_percentage': float(pnl_percentage),
                'leverage': float(position['leverage']),
                'margin': float(position['margin']),
                'liq_price': float(position['liq_price']),
                'distance_to_liq': float(pnl_percentage)
            })
            
        return positions
    
    def export_trades_to_csv(self, filename: str = "trades.csv"):
        """Export all trades to CSV file"""
        import csv
        
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = [
                'trade_id', 'symbol', 'side', 'entry_time', 'entry_price',
                'quantity', 'exit_time', 'exit_price', 'realized_pnl',
                'pnl_percentage', 'hold_time', 'status'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for trade in self.trades:
                writer.writerow({
                    'trade_id': trade['trade_id'],
                    'symbol': trade['symbol'],
                    'side': trade['side'],
                    'entry_time': trade['entry_time'],
                    'entry_price': float(trade['entry_price']),
                    'quantity': float(trade['quantity']),
                    'exit_time': trade['exit_time'],
                    'exit_price': float(trade['exit_price']) if trade['exit_price'] else None,
                    'realized_pnl': float(trade['realized_pnl']),
                    'pnl_percentage': float(trade['pnl_percentage']),
                    'hold_time': str(trade['hold_time']) if trade['hold_time'] else None,
                    'status': trade['status']
                })

# =====================================================================
# MAIN TRADING BOT CLASS
# =====================================================================

class TradingBot:
    def __init__(self, config: Config):
        self.config = config
        self.logger = setup_logger(config)
        
        # Initialize API sessions
        self.session = HTTP(
            testnet=config.TESTNET,
            api_key=config.API_KEY,
            api_secret=config.API_SECRET
        )
        
        # Initialize other managers
        self.precision = PrecisionManager(self.session, self.logger)
        self.sizing = OrderSizingCalculator(self.precision, self.logger)
        self.trailing = TrailingStopManager(self.session, self.precision, self.logger)
        self.pnl = PnLTracker(self.session, self.precision, self.logger)
        
        # Trading state
        self.in_position = False
        self.last_signal = Signal.NEUTRAL
        self.indicators = {}
        
        self.logger.info("Trading bot initialized")
    
    # =====================================================================
    # DATA FETCHING METHODS
    # =====================================================================
    
    def fetch_market_data(self) -> pd.DataFrame:
        """Fetch market data with error handling"""
        try:
            df = self.session.get_kline(
                category=self.config.CATEGORY,
                symbol=self.config.SYMBOL,
                interval=self.config.TIMEFRAME,
                limit=self.config.LOOKBACK_PERIODS
            )
            
            if df.empty:
                self.logger.warning("No market data available")
                return pd.DataFrame()
            
            # Process data
            df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            
            df = df.sort_values('timestamp').reset_index(drop=True)
            return df
            
        except Exception as e:
            self.logger.error(f"Error fetching market data: {e}")
            return pd.DataFrame()
    
    def calculate_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators with comprehensive error handling"""
        if df.empty:
            return df
        
        try:
            # Clear previous indicators
            self.indicators = {}
            
            # Trend Indicators
            df['ema_fast'] = ta.ema(df['close'], length=self.config.EMA_FAST)
            df['ema_slow'] = ta.ema(df['close'], length=self.config.EMA_SLOW)
            df['sma_20'] = ta.sma(df['close'], length=20)
            df['sma_50'] = ta.sma(df['close'], length=50)
            df['sma_200'] = ta.sma(df['close'], length=200)
            
            # MACD
            macd = ta.macd(
                df['close'],
                fast=self.config.MACD_FAST,
                slow=self.config.MACD_SLOW,
                signal=self.config.MACD_SIGNAL
            )
            df['macd'] = macd['MACD_' + str(self.config.MACD_FAST) + '_' + str(self.config.MACD_SLOW) + '_' + str(self.config.MACD_SIGNAL)]
            df['macd_signal'] = macd['MACDs_' + str(self.config.MACD_FAST) + '_' + str(self.config.MACD_SLOW) + '_' + str(self.config.MACD_SIGNAL)]
            df['macd_histogram'] = macd['MACDh_' + str(self.config.MACD_FAST) + '_' + str(self.config.MACD_SLOW) + '_' + str(self.config.MACD_SIGNAL)]
            
            # Momentum Indicators
            df['rsi'] = ta.rsi(df['close'], length=self.config.RSI_PERIOD)
            stoch = ta.stoch(df['high'], df['low'], df['close'])
            df['stoch_k'] = stoch['STOCHk_' + str(self.config.RSI_PERIOD) + '_3_3']
            df['stoch_d'] = stoch['STOCHd_' + str(self.config.RSI_PERIOD) + '_3_3']
            
            # Volatility Indicators
            df['bb_upper'] = ta.bbands(df['close'], length=self.config.BB_PERIOD, std=self.config.BB_STD)['BBU_' + str(self.config.BB_PERIOD) + '_' + str(self.config.BB_STD)]
            df['bb_middle'] = ta.bbands(df['close'], length=self.config.BB_PERIOD, std=self.config.BB_STD)['BBM_' + str(self.config.BB_PERIOD) + '_' + str(self.config.BB_STD)]
            df['bb_lower'] = ta.bbands(df['close'], length=self.config.BB_PERIOD, std=self.config.BB_STD)['BBL_' + str(self.config.BB_PERIOD) + '_' + str(self.config.BB_STD)]
            df['bb_width'] = ta.bbands(df['close'], length=self.config.BB_PERIOD, std=self.config.BB_STD)['BBB_' + str(self.config.BB_PERIOD) + '_' + str(self.config.BB_STD)]
            df['bb_percent'] = ta.bbands(df['close'], length=self.config.BB_PERIOD, std=self.config.BB_STD)['BBP_' + str(self.config.BB_PERIOD) + '_' + str(self.config.BB_STD)]
            df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=self.config.ATR_PERIOD)
            
            # Volume Indicators
            df['obv'] = ta.obv(df['close'], df['volume'])
            df['volume_sma'] = ta.sma(df['volume'], length=20)
            df['mfi'] = ta.mfi(df['high'], df['low'], df['close'], df['volume'], length=14)
            df['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
            
            # Support/Resistance
            pivots = ta.pivots(df['high'], df['low'], df['close'])
            if pivots is not None:
                df = pd.concat([df, pivots], axis=1)
            
            # Custom indicators
            df['price_change'] = df['close'].pct_change()
            df['ema_cross'] = np.where(
                df[f'ema_{self.config.EMA_FAST}'] > df[f'ema_{self.config.EMA_SLOW}'], 1, -1
            )
            
            # Drop NaN values
            df = df.fillna(method='ffill').fillna(0)
            
            self.logger.debug("Indicators calculated successfully")
            return df
            
        except Exception as e:
            self.logger.error(f"Error calculating indicators: {e}")
            return df
    
    # =====================================================================
    # STRATEGY LOGIC
    # =====================================================================
    
    def generate_signal(self, df: pd.DataFrame) -> Signal:
        """Generate trading signal using multiple indicators"""
        if df.empty or len(df) < 50:
            return Signal.NEUTRAL
        
        try:
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            signals = []
            
            # EMA Crossover
            if latest[f'ema_{self.config.EMA_FAST}'] > latest[f'ema_{self.config.EMA_SLOW}']:
                if prev[f'ema_{self.config.EMA_FAST}'] <= prev[f'ema_{self.config.EMA_SLOW}']:
                    signals.append(Signal.STRONG_BUY)
                else:
                    signals.append(Signal.BUY)
            elif latest[f'ema_{self.config.EMA_FAST}'] < latest[f'ema_{self.config.EMA_SLOW}']:
                if prev[f'ema_{self.config.EMA_FAST}'] >= prev[f'ema_{self.config.EMA_SLOW}']:
                    signals.append(Signal.STRONG_SELL)
                else:
                    signals.append(Signal.SELL)
            
            # RSI
            if latest['rsi'] < self.config.RSI_OVERSOLD:
                signals.append(Signal.BUY)
            elif latest['rsi'] > self.config.RSI_OVERBOUGHT:
                signals.append(Signal.SELL)
            
            # MACD
            if latest['macd'] > latest['macd_signal']:
                if prev['macd'] <= prev['macd_signal']:
                    signals.append(Signal.STRONG_BUY)
                else:
                    signals.append(Signal.BUY)
            elif latest['macd'] < latest['macd_signal']:
                if prev['macd'] >= prev['macd_signal']:
                    signals.append(Signal.STRONG_SELL)
                else:
                    signals.append(Signal.SELL)
            
            # Bollinger Bands
            if latest['close'] < latest['bb_lower']:
                signals.append(Signal.BUY)
            elif latest['close'] > latest['bb_upper']:
                signals.append(Signal.SELL)
            
            # Stochastic
            if latest['stoch_k'] < 20 and latest['stoch_d'] < 20:
                signals.append(Signal.BUY)
            elif latest['stoch_k'] > 80 and latest['stoch_d'] > 80:
                signals.append(Signal.SELL)
            
            # Aggregate signals
            if not signals:
                return Signal.NEUTRAL
            
            avg_signal = np.mean([s.value for s in signals])
            
            if avg_signal >= 1.5:
                return Signal.STRONG_BUY
            elif avg_signal >= 0.5:
                return Signal.BUY
            elif avg_signal <= -1.5:
                return Signal.STRONG_SELL
            elif avg_signal <= -0.5:
                return Signal.SELL
            else:
                return Signal.NEUTRAL
                
        except Exception as e:
            self.logger.error(f"Error generating signal: {e}")
            return Signal.NEUTRAL
    
    # =====================================================================
    # RISK MANAGEMENT
    # =====================================================================
    
    def execute_trade(self, signal: Signal):
        """Execute trade based on signal"""
        try:
            if not self.check_daily_loss_limit():
                self.logger.warning("Daily loss limit reached")
                return
            
            ticker = self.session.get_tickers(
                category=self.config.CATEGORY,
                symbol=self.config.SYMBOL
            )
            
            if not ticker:
                return
            
            current_price = float(ticker['lastPrice'])
            
            if signal in [Signal.BUY, Signal.STRONG_BUY] and not self.in_position:
                stop_loss = current_price * (1 - self.config.STOP_LOSS_PCT)
                take_profit = current_price * (1 + self.config.TAKE_PROFIT_PCT)
                position_size = self.sizing.calculate_position_size(
                    current_price, stop_loss, self.config.LEVERAGE
                )
                
                if position_size > 0:
                    result = self.place_order(
                        side="Buy",
                        qty=float(position_size),
                        order_type=self.config.ORDER_TYPE,
                        price=current_price * 0.9995,
                        stop_loss=stop_loss,
                        take_profit=take_profit
                    )
                    
                    if result:
                        self.in_position = True
                        self.last_signal = signal
                        self.logger.info(f"BUY executed at {current_price}")
                        
            elif signal in [Signal.SELL, Signal.STRONG_SELL] and self.in_position:
                self.close_position()
                self.logger.info(f"SELL executed at {current_price}")
                
        except Exception as e:
            self.logger.error(f"Error executing trade: {e}")
    
    # =====================================================================
    # POSITION MANAGEMENT
    # =====================================================================
    
    def close_position(self):
        """Close current position"""
        try:
            if not self.in_position:
                return
                
            position = self.positions.get(self.config.SYMBOL)
            if not position:
                return
                
            side = "Sell" if position['side'] == "Buy" else "Buy"
            qty = float(position['size'])
            
            result = self.place_order(
                side=side,
                qty=qty,
                order_type="Market"
            )
            
            if result:
                self.in_position = False
                self.last_signal = Signal.NEUTRAL
                self.logger.info(f"Position closed")
                
        except Exception as e:
            self.logger.error(f"Error closing position: {e}")
    
    # =====================================================================
    # MAIN EXECUTION LOOP
    # =====================================================================
    
    def run_strategy(self):
        """Main strategy execution loop"""
        try:
            while True:
                try:
                    # Fetch and process market data
                    df = self.fetch_market_data()
                    if not df.empty:
                        df = self.calculate_technical_indicators(df)
                        signal = self.generate_signal(df)
                        
                        self.logger.info(f"Signal: {signal.name}, Balance: {self.account_balance:.2f}")
                        
                        # Execute trade if signal is not neutral
                        if signal != Signal.NEUTRAL:
                            self.execute_trade(signal)
                            
                        # Update trailing stop if in position
                        if self.in_position:
                            self.trailing.update_trailing_stop(
                                self.config.SYMBOL, 
                                self.positions[self.config.SYMBOL]['side'],
                                self.positions[self.config.SYMBOL]['markPrice'],
                                self.config.TRAILING_STOP_PCT
                            )
                            
                except KeyboardInterrupt:
                    self.logger.info("Bot stopped by user")
                    break
                except Exception as e:
                    self.logger.error(f"Error in main loop: {e}")
                    time.sleep(self.config.LOOP_INTERVAL)
                    
        except Exception as e:
            self.logger.critical(f"Critical error: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup resources before exit"""
        try:
            # Cancel all orders
            self.cancel_all_orders()
            
            # Close WebSocket connections
            if hasattr(self, 'ws'):
                self.ws.exit()
                
            final_balance = self.get_account_balance()
            total_pnl = final_balance - self.start_balance
            self.logger.info("="*50)
            self.logger.info("Trading bot stopped")
            self.logger.info(f"Final Balance: {final_balance:.2f} USDT")
            self.logger.info(f"Total PnL: {total_pnl:.2f} USDT ({total_pnl/self.start_balance*100:.2f}%)")
            self.logger.info("="*50)
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

# =====================================================================
# USAGE EXAMPLE
# =====================================================================

if __name__ == "__main__":
    # Create and run the bot
    bot = TradingBot(Config())
    bot.run_strategy()
    

Below is the complete collection of Bybit V5 API functions organized by category, including WebSocket functions, order management, market data, and utility functions:

```json
{
  "websockets": {
    "connection": {
      "initialize": "Creates a WebSocket connection to Bybit's real-time data feed",
      "parameters": {
        "testnet": "Boolean flag for testnet/mainnet",
        "channel_type": "String specifying data category ('linear', 'spot', 'inverse', 'option')",
        "api_key": "Your API key",
        "api_secret": "Your API secret"
      }
    },
    "streams": {
      "kline_stream": {
        "description": "Subscribe to real-time kline/candlestick data",
        "format": "kline.{interval}.{symbol}",
        "example": "kline.5.BTCUSDT",
        "intervals_available": ["1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"]
      },
      "ticker_stream": {
        "description": "Subscribe to real-time ticker updates",
        "format": "tickers.{symbol}",
        "example": "tickers.BTCUSDT"
      },
      "orderbook_stream": {
        "description": "Subscribe to real-time order book depth",
        "format": "orderbook.{depth}.{symbol}",
        "depth_options": ["1", "25", "50", "100", "200", "500"]
      },
      "trade_stream": {
        "description": "Subscribe to real-time public trades",
        "format": "publicTrade.{symbol}"
      },
      "liquidation_stream": {
        "description": "Subscribe to real-time liquidation data",
        "format": "liquidation.{symbol}"
      },
      "position_stream": {
        "description": "Subscribe to real-time position updates (requires authentication)",
        "authentication_required": true
      },
      "order_stream": {
        "description": "Subscribe to real-time order updates (requires authentication)",
        "authentication_required": true
      },
      "execution_stream": {
        "description": "Subscribe to real-time trade execution updates (requires authentication)",
        "authentication_required": true
      },
      "wallet_stream": {
        "description": "Subscribe to real-time wallet balance updates (requires authentication)",
        "authentication_required": true
      }
    },
    "management": {
      "ping_pong": {
        "description": "Send periodic ping messages to keep connection alive",
        "frequency": "Every 20 seconds"
      }
    }
  },
  "order_placement": {
    "market_order": {
      "description": "Place a market order that executes immediately at current market price",
      "endpoint": "/v5/order/create",
      "required_parameters": {
        "category": "String (linear, spot, inverse, option)",
        "symbol": "Trading pair (e.g., BTCUSDT)",
        "side": "Buy or Sell",
        "qty": "Order quantity"
      },
      "optional_parameters": {
        "stopLoss": "Stop loss price",
        "takeProfit": "Take profit price",
        "tpslMode": "Full or Partial"
      }
    },
    "limit_order": {
      "description": "Place a limit order with specified price",
      "endpoint": "/v5/order/create",
      "required_parameters": {
        "category": "String (linear, spot, inverse, option)",
        "symbol": "Trading pair",
        "side": "Buy or Sell",
        "orderType": "Limit",
        "price": "Limit price",
        "qty": "Order quantity"
      },
      "optional_parameters": {
        "timeInForce": "GTC, IOC, FOK, PostOnly",
        "orderLinkId": "Custom order ID (max 36 chars)"
      }
    },
    "conditional_order": {
      "description": "Place a conditional order that triggers when price reaches a certain level",
      "endpoint": "/v5/order/create",
      "required_parameters": {
        "category": "String (linear, spot, inverse, option)",
        "symbol": "Trading pair",
        "orderType": "Limit",
        "triggerPrice": "Price level to trigger order",
        "side": "Buy or Sell"
      },
      "optional_parameters": {
        "triggerDirection": "1 (rise) or 2 (fall)",
        "triggerBy": "LastPrice, IndexPrice, MarkPrice"
      }
    },
    "stop_loss_take_profit": {
      "description": "Place order with predefined stop loss and take profit levels",
      "endpoint": "/v5/order/create",
      "required_parameters": {
        "category": "String (linear, spot, inverse, option)",
        "symbol": "Trading pair",
        "side": "Buy or Sell",
        "orderType": "Market",
        "qty": "Order quantity"
      },
      "optional_parameters": {
        "stopLoss": "Stop loss price",
        "takeProfit": "Take profit price",
        "tpTriggerBy": "MarkPrice, LastPrice, IndexPrice",
        "slTriggerBy": "MarkPrice, LastPrice, IndexPrice"
      }
    },
    "batch_operations": {
      "place_batch_order": {
        "description": "Place multiple orders in bulk (currently only supported for USDC Options)",
        "endpoint": "/v5/order/create-batch",
        "required_parameters": {
          "category": "option",
          "request": "List of order dictionaries"
        }
      },
      "amend_batch_order": {
        "description": "Modify multiple orders in bulk",
        "endpoint": "/v5/order/amend-batch",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "request": "List of amendment requests"
        }
      },
      "cancel_batch_order": {
        "description": "Cancel multiple orders in bulk",
        "endpoint": "/v5/order/cancel-batch",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "request": "List of order IDs to cancel"
        }
      }
    }
  },
  "position_management": {
    "position_queries": {
      "get_positions": {
        "description": "Get all open positions",
        "endpoint": "/v5/position/list",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair (optional)"
        }
      },
      "get_closed_pnl": {
        "description": "Get closed P&L records",
        "endpoint": "/v5/position/closed-pnl",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair (optional)",
          "startTime": "Start timestamp (ms)",
          "endTime": "End timestamp (ms)"
        }
      }
    },
    "position_configuration": {
      "set_leverage": {
        "description": "Adjust position leverage",
        "endpoint": "/v5/position/set-leverage",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair",
          "buyLeverage": "Buy side leverage",
          "sellLeverage": "Sell side leverage"
        }
      },
      "switch_margin_mode": {
        "description": "Switch between Cross/Isolated margin",
        "endpoint": "/v5/position/switch-isolated",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair (optional)",
          "mode": "0 (Merged Single) or 3 (Both Sides)"
        }
      },
      "set_trading_stop": {
        "description": "Set position stop loss",
        "endpoint": "/v5/position/trading-stop",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair",
          "stopLoss": "Stop loss price",
          "tpTriggerBy": "MarkPrice, LastPrice, IndexPrice",
          "slTriggerBy": "MarkPrice, LastPrice, IndexPrice",
          "positionIdx": "0 (one-way), 1 (buy-side), 2 (sell-side)"
        }
      },
      "set_risk_limit": {
        "description": "Set risk limit",
        "endpoint": "/v5/position/set-risk-limit",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair",
          "riskId": "Risk limit ID"
        }
      },
      "add_margin": {
        "description": "Add/reduce margin",
        "endpoint": "/v5/position/add-margin",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair",
          "amount": "Margin amount to add"
        }
      }
    },
  },
  "account_and_wallet_functions": {
    "account_information": {
      "get_wallet_balance": {
        "description": "Get wallet balance",
        "endpoint": "/v5/account/wallet-balance",
        "required_parameters": {
          "accountType": "UNIFIED or CONTRACT"
        }
      },
      "get_account_info": {
        "description": "Get account information",
        "endpoint": "/v5/account/info"
      },
      "get_fee_rate": {
        "description": "View trading fee rates",
        "endpoint": "/v5/account/fee-rate",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair (optional)"
        }
      },
      "get_transaction_log": {
        "description": "Get transaction history",
        "endpoint": "/v5/account/transaction-log",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair (optional)",
          "startTime": "Start timestamp (ms)",
          "endTime": "End timestamp (ms)"
        }
      }
    },
  },
  "market_data_functions": {
    "public_market_data": {
      "get_tickers": {
        "description": "Get latest price snapshots",
        "endpoint": "/v5/market/tickers",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair (optional)"
        }
      },
      "get_orderbook": {
        "description": "Retrieve order book depth",
        "endpoint": "/v5/market/orderbook",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair",
          "limit": "Depth (1, 25, 50, 100, 200, 500)"
        }
      },
      "get_kline": {
        "description": "Get historical candlestick data",
        "endpoint": "/v5/market/kline",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair",
          "interval": "Time interval (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)",
          "start": "Start timestamp (ms)",
          "end": "End timestamp (ms)",
          "limit": "Number of results (default: 200, max: 1000)"
        }
      },
      "get_mark_price_kline": {
        "description": "Get mark price kline",
        "endpoint": "/v5/market/mark-price-kline",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair",
          "interval": "Time interval (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)",
          "start": "Start timestamp (ms)",
          "end": "End timestamp (ms)",
          "limit": "Number of results (default: 200, max: 1000)"
        }
      },
      "get_index_price_kline": {
        "description": "Get index price kline",
        "endpoint": "/v5/market/index-price-kline",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair",
          "interval": "Time interval (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)",
          "start": "Start timestamp (ms)",
          "end": "End timestamp (ms)",
          "limit": "Number of results (default: 200, max: 1000)"
        }
      },
      "get_premium_index_price_kline": {
        "description": "Get premium index kline",
        "endpoint": "/v5/market/premium-index-price-kline",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair",
          "interval": "Time interval (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)",
          "start": "Start timestamp (ms)",
          "end": "End timestamp (ms)",
          "limit": "Number of results (default: 200, max: 1000)"
        }
      },
      "get_public_trading_history": {
        "description": "Get recent trades",
        "endpoint": "/v5/market/recent-trade",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair"
        }
      },
      "get_liquidation_stream": {
        "description": "Get real-time liquidations",
        "endpoint": "/v5/market/liquidation-stream",
        "required_parameters": {
          "category": "String (linear, spot, inverse, option)",
          "symbol": "Trading pair"
        }
      }
    },
    "legacy_pybit_functions": {
      "place_active_order": "Deprecated function for active orders",
      "cancel_active_order": "Deprecated function for active orders",
      "place_conditional_order": "Deprecated function for conditional orders",
      "cancel_conditional_order": "Deprecated function for conditional orders",
      "query_active_order": "Deprecated function for active orders",
      "query_conditional_order": "Deprecated function for conditional orders",
      "replace_active_order": "Deprecated function for replacing active orders"
    },
    "order_parameters": {
      "required_parameters": {
        "category": "String (linear, spot, inverse, option)",
        "symbol": "Trading pair",
        "side": "Buy or Sell",
        "orderType": "Limit or Market",
        "qty": "Order quantity"
      },
      "optional_parameters": {
        "price": "Required for limit orders",
        "timeInForce": "GTC, IOC, FOK, PostOnly",
        "orderLinkId": "Custom order ID (max 36 characters)",
        "positionIdx": "0 (one-way), 1 (buy-side), 2 (sell-side)",
        "reduceOnly": "true/false",
        "closeOnTrigger": "true/false",
        "triggerPrice": "For conditional orders",
        "triggerBy": "LastPrice, IndexPrice, MarkPrice",
        "tpslMode": "Full or Partial",
        "takeProfit": "Take profit price",
        "stopLoss": "Stop loss price"
      },
      "rate_limits": {
        "market_data": "120 requests per minute",
        "order_management": "60 requests per minute",
        "position_queries": "120 requests per minute"
      },
      "best_practices": [
        "Use WebSocket for real-time updates",
        "Implement proper error handling",
        "Set leverage and margin mode before placing orders",
        "Use orderLinkId for tracking orders",
        "Check decimal precision for each symbol before placing orders",
        "Test on testnet before deploying to production",
        "Use WebSocket for real-time data instead of polling",
        "Implement rate limiting",
        "Keep logs of all orders and trades",
        "Implement position size management",
        "Use proper risk management with stop losses"
      ]
    }
  }
}
```

This comprehensive JSON structure organizes all the key Bybit V5 API functions into logical categories, making it easy to understand and integrate into trading bot implementations. The structure covers:

1. **Websocket Functions** - Real-time data streams for klines, tickers, orderbooks, and more
2. **Order Management** - Market/Limit orders, stop loss/take profit, conditional orders, and batch operations
3. **Market Data Functions** - Klines, tickers, orderbooks, and other market data endpoints
4. **Utility Functions** - Account management, position queries, and helper functions

Each section includes detailed descriptions of parameters, examples, and best practices for implementation.