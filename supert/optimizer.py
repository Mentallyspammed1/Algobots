import logging
from datetime import datetime
from decimal import Decimal, getcontext

import optuna
import pandas as pd

from backtester import BybitHistoricalDataDownloader

# Assuming stupdated2.py and backtester.py are in the same directory
from stupdated2 import Config, EhlersSuperTrendBot

# Set precision for Decimal
getcontext().prec = 28

# --- Basic Logger Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BotBacktester:
    """
    A dedicated backtester for the EhlersSuperTrendBot.
    It simulates the bot's logic on historical data without making live API calls.
    """
    def __init__(self, config: Config, historical_data: pd.DataFrame):
        self.config = config
        self.historical_data = historical_data

        # --- Isolate the bot from the network ---
        self.bot = EhlersSuperTrendBot(config)
        self.bot.api_call = self.mock_api_call
        self.bot.precision_manager.load_all_instruments = self.mock_load_all_instruments
        self.bot.precision_manager.get_specs = self.mock_get_specs
        self.bot._validate_api_credentials = lambda: True
        self.bot._configure_trading_parameters = lambda: True
        self.bot._capture_initial_equity = lambda: True

        # --- Backtest state ---
        self.initial_capital = Decimal('10000.0')
        self.capital = self.initial_capital
        self.equity_curve = []
        self.trades = []
        self.position = None # To hold the current open trade

    # --- Mock Methods to Prevent Live API Calls ---
    def mock_api_call(self, api_method, **kwargs):
        logger.debug(f"Mock API call intercepted for {api_method.__name__} with args {kwargs}")
        return None # Prevent any real API calls

    def mock_load_all_instruments(self):
        logger.debug("Mocked loading of all instruments.")

    def mock_get_specs(self, symbol):
        """Return mock instrument specs to avoid API calls."""
        from stupdated2 import InstrumentSpecs
        return InstrumentSpecs(
            symbol=symbol, category='linear', base_currency='BTC', quote_currency='USDT',
            status='Trading', min_price=Decimal('0.01'), max_price=Decimal('1000000'),
            tick_size=Decimal('0.01'), min_order_qty=Decimal('0.001'), max_order_qty=Decimal('100'),
            qty_step=Decimal('0.001'), min_leverage=Decimal('1'), max_leverage=Decimal('100'),
            leverage_step=Decimal('0.01'), max_position_value=Decimal('2000000'),
            min_position_value=Decimal('1')
        )

    def run(self):
        """Executes the backtest from start to finish."""
        logger.info("Starting backtest run...")

        self.bot.market_data = self.historical_data
        self.bot.market_data = self.bot.calculate_indicators(self.bot.market_data)

        if self.bot.market_data.empty:
            logger.error("Indicator calculation resulted in empty dataframe. Aborting backtest.")
            return 0.0

        for i in range(1, len(self.bot.market_data)):
            current_candle = self.bot.market_data.iloc[i]
            self.bot.account_balance_usdt = self.capital # Update bot's balance

            self._check_exit_conditions(current_candle)

            if not self.position:
                self._check_entry_conditions(i)

            self.equity_curve.append(self.capital)

        return self._calculate_performance()

    def _check_exit_conditions(self, candle):
        if not self.position: return
        exit_price, exit_reason = None, None
        if self.position['side'] == 'Buy':
            if candle['low'] <= float(self.position['stop_loss']):
                exit_price, exit_reason = self.position['stop_loss'], 'SL'
            elif candle['high'] >= float(self.position['take_profit']):
                exit_price, exit_reason = self.position['take_profit'], 'TP'
        elif self.position['side'] == 'Sell':
            if candle['high'] >= float(self.position['stop_loss']):
                exit_price, exit_reason = self.position['stop_loss'], 'SL'
            elif candle['low'] <= float(self.position['take_profit']):
                exit_price, exit_reason = self.position['take_profit'], 'TP'

        if not exit_price and ( (self.position['side'] == 'Buy' and candle['supertrend_direction'] == -1) or (self.position['side'] == 'Sell' and candle['supertrend_direction'] == 1) ):
            exit_price, exit_reason = candle['close'], 'Signal Reversal'

        if exit_price:
            self._close_position(candle.name, exit_price, exit_reason)

    def _check_entry_conditions(self, index):
        df_slice = self.bot.market_data.iloc[:index+1]
        signal, _ = self.bot.generate_signal(df_slice)

        if signal in ['BUY', 'SELL']:
            entry_price = df_slice['close'].iloc[-1]
            trade_side = 'Buy' if signal == 'BUY' else 'Sell'
            sl_price, tp_price = self.bot.calculate_trade_sl_tp(trade_side, Decimal(str(entry_price)), df_slice)
            risk_per_trade = self.capital * (Decimal(self.config.RISK_PER_TRADE_PCT) / Decimal(100))
            stop_distance = abs(Decimal(str(entry_price)) - sl_price)
            if stop_distance > 0:
                quantity = risk_per_trade / stop_distance
                if quantity > 0:
                    self._open_position(df_slice.index[-1], trade_side, entry_price, sl_price, tp_price, quantity)

    def _open_position(self, time, side, entry_price, sl, tp, qty):
        self.position = {'entry_time': time, 'side': side, 'entry_price': Decimal(str(entry_price)), 'stop_loss': sl, 'take_profit': tp, 'quantity': qty}
        logger.debug(f"Opened {side} position at {entry_price} on {time}")

    def _close_position(self, time, exit_price, reason):
        entry_price = self.position['entry_price']
        quantity = self.position['quantity']
        pnl = (Decimal(str(exit_price)) - entry_price) * quantity if self.position['side'] == 'Buy' else (entry_price - Decimal(str(exit_price))) * quantity
        pnl -= (entry_price * quantity + Decimal(str(exit_price)) * quantity) * Decimal('0.0006')
        self.capital += pnl
        self.trades.append({'entry_time': self.position['entry_time'], 'exit_time': time, 'side': self.position['side'], 'pnl': pnl})
        logger.debug(f"Closed {self.position['side']} position at {exit_price} on {time}. PnL: {pnl:.2f}")
        self.position = None

    def _calculate_performance(self):
        if not self.equity_curve:
            return 0.0
        equity_series = pd.Series([float(e) for e in self.equity_curve])
        total_return_pct = (equity_series.iloc[-1] / float(self.initial_capital)) - 1.0
        logger.info(f"Backtest finished. Total Return: {total_return_pct:.2%}")
        return total_return_pct

def objective(trial: optuna.trial.Trial, historical_data: pd.DataFrame, symbol: str):
    config = Config()
    config.SYMBOL = symbol # Ensure bot uses the correct symbol
    config.EHLERS_ST_LENGTH = trial.suggest_int('EHLERS_ST_LENGTH', 7, 20)
    config.EHLERS_ST_MULTIPLIER = trial.suggest_float('EHLERS_ST_MULTIPLIER', 1.5, 4.0)
    config.STOP_LOSS_PCT = trial.suggest_float('STOP_LOSS_PCT', 0.01, 0.05)
    config.TAKE_PROFIT_PCT = trial.suggest_float('TAKE_PROFIT_PCT', 0.015, 0.08)
    config.RSI_WINDOW = trial.suggest_int('RSI_WINDOW', 8, 21)
    config.ADX_TREND_FILTER_ENABLED = trial.suggest_categorical('ADX_TREND_FILTER_ENABLED', [True, False])
    if config.ADX_TREND_FILTER_ENABLED:
        config.ADX_MIN_THRESHOLD = trial.suggest_int('ADX_MIN_THRESHOLD', 20, 30)
    config.DRY_RUN = True
    config.TESTNET = True
    config.LOG_LEVEL = "ERROR"
    backtester = BotBacktester(config, historical_data.copy())
    return backtester.run()

def main():
    logger.info("Starting Ehlers SuperTrend Bot Optimization...")
    downloader = BybitHistoricalDataDownloader(testnet=False)
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

    study_name = "ehlers_supertrend_optimization_v3"
    storage = f"sqlite:///{study_name}.db"
    study = optuna.create_study(study_name=study_name, storage=storage, direction='maximize', load_if_exists=True)
    objective_with_data = lambda trial: objective(trial, historical_data, symbol)
    logger.info(f"Starting Optuna study. Dashboard: `optuna-dashboard {storage}`")
    study.optimize(objective_with_data, n_trials=200)

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
