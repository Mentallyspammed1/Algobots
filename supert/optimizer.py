
import optuna
import pandas as pd
from datetime import datetime
import logging
import numpy as np
from decimal import Decimal

# Assuming stupdated2.py and backtester.py are in the same directory
from stupdated2 import EhlersSuperTrendBot, Config, OrderType
from backtester import BybitHistoricalDataDownloader

# --- Basic Logger Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BotBacktester:
    """
    A dedicated backtester for the EhlersSuperTrendBot.
    It simulates the bot's logic on historical data.
    """
    def __init__(self, config: Config, historical_data: pd.DataFrame):
        self.config = config
        self.historical_data = historical_data
        self.bot = EhlersSuperTrendBot(config)
        
        # Backtest state
        self.initial_capital = Decimal('10000.0')
        self.capital = self.initial_capital
        self.equity_curve = []
        self.trades = []
        self.position = None # To hold the current open trade

    def run(self):
        """Executes the backtest from start to finish."""
        logger.info("Starting backtest run...")

        # 1. Prepare data with indicators
        self.bot.market_data = self.historical_data
        self.bot.market_data = self.bot.calculate_indicators(self.bot.market_data)
        
        if self.bot.market_data.empty:
            logger.error("Indicator calculation resulted in empty dataframe. Aborting backtest.")
            return 0.0

        # 2. Loop through historical data
        for i in range(1, len(self.bot.market_data)):
            current_candle = self.bot.market_data.iloc[i]
            self.bot.account_balance_usdt = self.capital # Update bot's balance

            # Simulate checking for exits first
            self._check_exit_conditions(current_candle)

            # Simulate checking for entries
            if not self.position:
                self._check_entry_conditions(i)
            
            self.equity_curve.append(self.capital)

        # 3. Calculate final performance
        return self._calculate_performance()

    def _check_exit_conditions(self, candle):
        """Checks and executes exit conditions for an open position."""
        if not self.position:
            return

        exit_price = None
        exit_reason = None

        # Check SL/TP
        if self.position['side'] == 'Buy':
            if candle['low'] <= self.position['stop_loss']:
                exit_price = self.position['stop_loss']
                exit_reason = 'SL'
            elif candle['high'] >= self.position['take_profit']:
                exit_price = self.position['take_profit']
                exit_reason = 'TP'
        elif self.position['side'] == 'Sell':
            if candle['high'] >= self.position['stop_loss']:
                exit_price = self.position['stop_loss']
                exit_reason = 'SL'
            elif candle['low'] <= self.position['take_profit']:
                exit_price = self.position['take_profit']
                exit_reason = 'TP'
        
        # Check for signal reversal
        if not exit_price:
            latest_st_direction = candle['supertrend_direction']
            if (self.position['side'] == 'Buy' and latest_st_direction == -1) or \
               (self.position['side'] == 'Sell' and latest_st_direction == 1):
                exit_price = candle['close']
                exit_reason = 'Signal Reversal'

        if exit_price:
            self._close_position(candle.name, exit_price, exit_reason)

    def _check_entry_conditions(self, index):
        """Checks and executes entry conditions."""
        # The bot's signal logic requires a small slice of the dataframe
        df_slice = self.bot.market_data.iloc[:index+1]
        signal, reason = self.bot.generate_signal(df_slice)

        if signal in ['BUY', 'SELL']:
            entry_price = df_slice['close'].iloc[-1]
            trade_side = 'Buy' if signal == 'BUY' else 'Sell'
            
            sl_price, tp_price = self.bot.calculate_trade_sl_tp(trade_side, Decimal(str(entry_price)), df_slice)
            
            # Use a simplified position sizer for backtesting
            risk_per_trade = self.capital * Decimal(str(self.config.RISK_PER_TRADE_PCT / 100.0))
            stop_distance = abs(Decimal(str(entry_price)) - sl_price)
            
            if stop_distance > 0:
                quantity = (risk_per_trade / stop_distance)
            else:
                quantity = Decimal('0')

            if quantity > 0:
                self._open_position(df_slice.index[-1], trade_side, entry_price, sl_price, tp_price, quantity)

    def _open_position(self, time, side, entry_price, sl, tp, qty):
        """Simulates opening a new position."""
        self.position = {
            'entry_time': time,
            'side': side,
            'entry_price': Decimal(str(entry_price)),
            'stop_loss': sl,
            'take_profit': tp,
            'quantity': qty
        }
        logger.debug(f"Opened {side} position at {entry_price} on {time}")

    def _close_position(self, time, exit_price, reason):
        """Simulates closing the current position and records the trade."""
        entry_price = self.position['entry_price']
        quantity = self.position['quantity']
        
        pnl = Decimal('0')
        if self.position['side'] == 'Buy':
            pnl = (Decimal(str(exit_price)) - entry_price) * quantity
        else: # Sell
            pnl = (entry_price - Decimal(str(exit_price))) * quantity
        
        # Apply fees
        pnl -= (entry_price * quantity) * Decimal('0.0006') # Taker fee on entry
        pnl -= (Decimal(str(exit_price)) * quantity) * Decimal('0.0006') # Taker fee on exit

        self.capital += pnl
        
        self.trades.append({
            'entry_time': self.position['entry_time'],
            'exit_time': time,
            'side': self.position['side'],
            'pnl': pnl
        })
        logger.debug(f"Closed {self.position['side']} position at {exit_price} on {time}. PnL: {pnl:.2f}")
        self.position = None

    def _calculate_performance(self):
        """Calculates and returns the final performance metric."""
        if self.initial_capital == 0:
            return 0.0
        total_return_pct = (self.capital - self.initial_capital) / self.initial_capital
        
        # For Optuna, we want a single metric to optimize.
        # A simple metric is total return, but Sharpe ratio is often better.
        returns = pd.Series(self.equity_curve).pct_change().dropna()
        if returns.std() > 0:
            sharpe_ratio = returns.mean() / returns.std() * np.sqrt(365 * 24 * 4) # For 15min data
        else:
            sharpe_ratio = 0.0
            
        # We will optimize for total return for simplicity now.
        logger.info(f"Backtest finished. Total Return: {total_return_pct:.2%}")
        return float(total_return_pct)


def objective(trial: optuna.trial.Trial, historical_data: pd.DataFrame):
    """
    The objective function for Optuna to optimize.
    """
    config = Config()

    # --- Define Search Space ---
    config.EHLERS_ST_LENGTH = trial.suggest_int('EHLERS_ST_LENGTH', 7, 20)
    config.EHLERS_ST_MULTIPLIER = trial.suggest_float('EHLERS_ST_MULTIPLIER', 1.5, 4.0)
    config.STOP_LOSS_PCT = trial.suggest_float('STOP_LOSS_PCT', 0.01, 0.05)
    config.TAKE_PROFIT_PCT = trial.suggest_float('TAKE_PROFIT_PCT', 0.015, 0.08)
    config.RSI_WINDOW = trial.suggest_int('RSI_WINDOW', 8, 21)
    config.ADX_MIN_THRESHOLD = trial.suggest_int('ADX_MIN_THRESHOLD', 20, 30)
    
    # --- Set static config for backtesting ---
    config.DRY_RUN = True
    config.TESTNET = True
    config.LOG_LEVEL = "WARNING" # Reduce noise during optimization

    # --- Run Backtest ---
    backtester = BotBacktester(config, historical_data.copy())
    performance = backtester.run()

    return performance

def main():
    """
    Main function to run the optimization.
    """
    logger.info("Starting Ehlers SuperTrend Bot Optimization...")

    # --- 1. Load Historical Data ---
    downloader = BybitHistoricalDataDownloader(testnet=True)
    symbol = "BTCUSDT"
    timeframe = "15"
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 7, 1)
    
    data_filename = f"{symbol}_{timeframe}_data.csv"
    try:
        historical_data = pd.read_csv(data_filename, index_col='timestamp', parse_dates=True)
        logger.info(f"Loaded historical data from {data_filename}")
    except FileNotFoundError:
        logger.info("Data file not found. Downloading from Bybit...")
        historical_data = downloader.fetch_historical_klines(symbol, timeframe, start_date, end_date)
        downloader.save_to_csv(historical_data, data_filename)

    if historical_data.empty:
        logger.error("Failed to load historical data. Exiting.")
        return

    # --- 2. Run Optuna Optimization ---
    study_name = "ehlers_supertrend_optimization_v2"
    storage = "sqlite:///ehlers_supertrend_v2.db"
    
    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        direction='maximize',
        load_if_exists=True
    )

    objective_with_data = lambda trial: objective(trial, historical_data)

    logger.info(f"Starting Optuna study. Visit `optuna-dashboard {storage}` to monitor.")
    study.optimize(objective_with_data, n_trials=200)

    # --- 3. Print Results ---
    logger.info("Optimization finished.")
    df_results = study.trials_dataframe()
    logger.info(f"Top 5 Trials:\n{df_results.sort_values('value', ascending=False).head()}")

    best_trial = study.best_trial
    logger.info("\n--- Best Trial ---")
    logger.info(f"  Value (Total Return %): {best_trial.value:.2%}")
    logger.info("  Params: ")
    for key, value in best_trial.params.items():
        logger.info(f"    {key}: {value}")

if __name__ == "__main__":
    main()
