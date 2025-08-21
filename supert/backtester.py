import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
from pybit.unified_trading import HTTP
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from itertools import product
import multiprocessing as mp
from functools import partial
import matplotlib.pyplot as plt
import seaborn as sns
import pandas_ta as ta
from decimal import Decimal


class BybitHistoricalDataDownloader:
    """Download historical kline data from Bybit V5 API"""

    def __init__(self, testnet=True):
        self.session = HTTP(testnet=testnet)

    def fetch_historical_klines(self, symbol, interval, start_date, end_date, category='linear'):
        """
        Fetch historical kline data for backtesting

        Parameters:
        - symbol: Trading pair (e.g., 'BTCUSDT')
        - interval: Timeframe ('1', '3', '5', '15', '30', '60', '120', '240', '360', '720', 'D', 'W', 'M')
        - start_date: Start datetime
        - end_date: End datetime
        - category: Product category ('linear', 'spot', 'inverse')
        """
        all_klines = []
        current_end = end_date

        while current_end > start_date:
            # Bybit returns max 200-1000 bars per request
            response = self.session.get_kline(
                category=category,
                symbol=symbol,
                interval=interval,
                end=int(current_end.timestamp() * 1000),
                limit=1000
            )

            if response['retCode'] == 0:
                klines = response['result']['list']

                if not klines:
                    break

                # Convert to DataFrame
                df_batch = pd.DataFrame(klines, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
                ])

                # Convert timestamp to datetime
                df_batch['timestamp'] = pd.to_datetime(df_batch['timestamp'].astype(float), unit='ms')

                # Convert price columns to float
                for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                    df_batch[col] = df_batch[col].astype(float)

                all_klines.append(df_batch)

                # Update current_end to the oldest timestamp from this batch
                current_end = df_batch['timestamp'].min() - timedelta(minutes=1)

                # Rate limiting to avoid API restrictions
                time.sleep(0.1)

                print(f"Downloaded data up to {current_end}")

                # Break if we've reached the start date
                if current_end <= start_date:
                    break
            else:
                print(f"Error fetching data: {response.get('retMsg')}")
                break

        if all_klines:
            # Combine all batches
            df = pd.concat(all_klines, ignore_index=True)

            # Remove duplicates and sort by timestamp
            df = df.drop_duplicates(subset=['timestamp'])
            df = df.sort_values('timestamp')
            df = df.set_index('timestamp')

            # Filter to requested date range
            df = df[(df.index >= start_date) & (df.index <= end_date)]

            return df

        return pd.DataFrame()

    def save_to_csv(self, df, filename):
        """Save DataFrame to CSV file"""
        df.to_csv(filename)
        print(f"Data saved to {filename}")

@dataclass
class Trade:
    """Store individual trade information"""
    entry_time: datetime
    exit_time: Optional[datetime]
    side: str  # 'Buy' or 'Sell'
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    stop_loss: float
    take_profit: float
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    exit_reason: Optional[str] = None  # 'SL', 'TP', 'Signal', 'Trailing'

@dataclass
class BacktestResults:
    """Store backtest results and metrics"""
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_pct: float
    num_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    trades: List[Trade] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=pd.Series)

class SupertrendBacktester:
    """Backtest the Supertrend strategy with historical data"""

    def __init__(self, config):
        self.config = config
        self.trades = []
        self.equity_curve = []

    def calculate_indicators(self, df):
        """Calculate Supertrend and other indicators"""
        # Calculate ATR
        df['atr'] = ta.atr(df['high'], df['low'], df['close'],
                          length=self.config.ST_PERIOD)

        # Calculate Supertrend
        st = ta.supertrend(
            high=df['high'],
            low=df['low'],
            close=df['close'],
            length=self.config.ST_PERIOD,
            multiplier=self.config.ST_MULTIPLIER
        )

        # Merge Supertrend columns
        df = pd.concat([df, st], axis=1)

        # Generate signals
        df['signal'] = 0
        df.loc[df[f'SUPERTd_{self.config.ST_PERIOD}_{self.config.ST_MULTIPLIER}'] == 1, 'signal'] = 1
        df.loc[df[f'SUPERTd_{self.config.ST_PERIOD}_{self.config.ST_MULTIPLIER}'] == -1, 'signal'] = -1

        # Detect signal changes
        df['signal_change'] = df['signal'].diff()

        return df

    def calculate_position_size(self, capital, entry_price, stop_loss_price):
        """Calculate position size based on risk management"""
        risk_amount = capital * (self.config.RISK_PER_TRADE_PCT / 100)
        stop_distance = abs(entry_price - stop_loss_price)
        stop_distance_pct = stop_distance / entry_price if entry_price > 0 else 0

        if stop_distance_pct > 0:
            position_value = risk_amount / stop_distance_pct
            position_value = min(position_value, self.config.MAX_POSITION_SIZE_USD)
            position_value = max(position_value, self.config.MIN_POSITION_SIZE_USD)

            quantity = position_value / entry_price
            return quantity, position_value

        return 0, 0

    def run_backtest(self, df):
        """Run the backtest simulation"""
        df = self.calculate_indicators(df)

        capital = self.config.INITIAL_CAPITAL
        position = None
        trades = []
        equity_curve = [capital]

        for i in range(1, len(df)):
            current = df.iloc[i]
            previous = df.iloc[i-1]

            # Check for entry signals
            if position is None:
                # Buy signal
                if previous['signal'] == -1 and current['signal'] == 1:
                    entry_price = current['close']
                    stop_loss = entry_price * (1 - self.config.STOP_LOSS_PCT)
                    take_profit = entry_price * (1 + self.config.TAKE_PROFIT_PCT)

                    quantity, position_value = self.calculate_position_size(
                        capital, entry_price, stop_loss
                    )

                    if quantity > 0:
                        position = Trade(
                            entry_time=current.name,
                            exit_time=None,
                            side='Buy',
                            entry_price=entry_price,
                            exit_price=None,
                            quantity=quantity,
                            stop_loss=stop_loss,
                            take_profit=take_profit
                        )

                # Sell signal (for short positions if enabled)
                elif self.config.ALLOW_SHORT and previous['signal'] == 1 and current['signal'] == -1:
                    entry_price = current['close']
                    stop_loss = entry_price * (1 + self.config.STOP_LOSS_PCT)
                    take_profit = entry_price * (1 - self.config.TAKE_PROFIT_PCT)

                    quantity, position_value = self.calculate_position_size(
                        capital, entry_price, stop_loss
                    )

                    if quantity > 0:
                        position = Trade(
                            entry_time=current.name,
                            exit_time=None,
                            side='Sell',
                            entry_price=entry_price,
                            exit_price=None,
                            quantity=quantity,
                            stop_loss=stop_loss,
                            take_profit=take_profit
                        )

            # Check for exit conditions
            elif position is not None:
                exit_price = None
                exit_reason = None

                if position.side == 'Buy':
                    # Check stop loss
                    if current['low'] <= position.stop_loss:
                        exit_price = position.stop_loss
                        exit_reason = 'SL'
                    # Check take profit
                    elif current['high'] >= position.take_profit:
                        exit_price = position.take_profit
                        exit_reason = 'TP'
                    # Check signal reversal
                    elif current['signal'] == -1:
                        exit_price = current['close']
                        exit_reason = 'Signal'

                elif position.side == 'Sell':
                    # Check stop loss
                    if current['high'] >= position.stop_loss:
                        exit_price = position.stop_loss
                        exit_reason = 'SL'
                    # Check take profit
                    elif current['low'] <= position.take_profit:
                        exit_price = position.take_profit
                        exit_reason = 'TP'
                    # Check signal reversal
                    elif current['signal'] == 1:
                        exit_price = current['close']
                        exit_reason = 'Signal'

                # Execute exit
                if exit_price:
                    position.exit_time = current.name
                    position.exit_price = exit_price
                    position.exit_reason = exit_reason

                    # Calculate PnL
                    if position.side == 'Buy':
                        position.pnl = (exit_price - position.entry_price) * position.quantity
                        position.pnl_pct = ((exit_price - position.entry_price) / position.entry_price) * 100
                    else:  # Sell
                        position.pnl = (position.entry_price - exit_price) * position.quantity
                        position.pnl_pct = ((position.entry_price - exit_price) / position.entry_price) * 100

                    capital += position.pnl
                    trades.append(position)
                    position = None

            equity_curve.append(capital)

        # Close any open position at the end
        if position is not None:
            position.exit_time = df.index[-1]
            position.exit_price = df.iloc[-1]['close']
            position.exit_reason = 'End'

            if position.side == 'Buy':
                position.pnl = (position.exit_price - position.entry_price) * position.quantity
                position.pnl_pct = ((position.exit_price - position.entry_price) / position.entry_price) * 100
            else:
                position.pnl = (position.entry_price - position.exit_price) * position.quantity
                position.pnl_pct = ((position.entry_price - position.exit_price) / position.entry_price) * 100

            capital += position.pnl
            trades.append(position)

        # Calculate metrics
        results = self.calculate_metrics(trades, equity_curve, self.config.INITIAL_CAPITAL)
        return results

    def calculate_metrics(self, trades, equity_curve, initial_capital):
        """Calculate comprehensive backtest metrics"""
        if not trades:
            return BacktestResults(
                initial_capital=initial_capital,
                final_capital=initial_capital,
                total_return=0,
                total_return_pct=0,
                num_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0,
                avg_win=0,
                avg_loss=0,
                profit_factor=0,
                max_drawdown=0,
                max_drawdown_pct=0,
                sharpe_ratio=0,
                sortino_ratio=0,
                trades=[],
                equity_curve=pd.Series(equity_curve)
            )

        # Basic metrics
        final_capital = equity_curve[-1]
        total_return = final_capital - initial_capital
        total_return_pct = (total_return / initial_capital) * 100

        # Trade statistics
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl <= 0]

        num_trades = len(trades)
        num_winning = len(winning_trades)
        num_losing = len(losing_trades)
        win_rate = (num_winning / num_trades * 100) if num_trades > 0 else 0

        avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t.pnl for t in losing_trades]) if losing_trades else 0

        # Profit factor
        gross_profit = sum([t.pnl for t in winning_trades]) if winning_trades else 0
        gross_loss = abs(sum([t.pnl for t in losing_trades])) if losing_trades else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Drawdown calculation
        equity_series = pd.Series(equity_curve)
        cummax = equity_series.cummax()
        drawdown = (equity_series - cummax) / cummax
        max_drawdown_pct = drawdown.min() * 100
        max_drawdown = (equity_series - cummax).min()

        # Risk-adjusted returns
        returns = equity_series.pct_change().dropna()
        sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0

        downside_returns = returns[returns < 0]
        sortino_ratio = returns.mean() / downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 and downside_returns.std() > 0 else 0

        return BacktestResults(
            initial_capital=initial_capital,
            final_capital=final_capital,
            total_return=total_return,
            total_return_pct=total_return_pct,
            num_trades=num_trades,
            winning_trades=num_winning,
            losing_trades=num_losing,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            trades=trades,
            equity_curve=equity_series
        )

class ParameterOptimizer:
    """Optimize strategy parameters using grid search"""

    def __init__(self, data, base_config):
        self.data = data
        self.base_config = base_config

    def optimize_parameters(self, param_grid):
        """
        Run grid search optimization

        param_grid = {
            'ST_PERIOD': [7, 10, 14, 20],
            'ST_MULTIPLIER': [2.0, 2.5, 3.0, 3.5],
            'STOP_LOSS_PCT': [0.01, 0.015, 0.02],
            'TAKE_PROFIT_PCT': [0.02, 0.03, 0.04],
            'RISK_PER_TRADE_PCT': [0.5, 1.0, 1.5, 2.0]
        }
        """
        # Generate all parameter combinations
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        combinations = list(product(*values))

        results = []

        for combo in combinations:
            # Create config with current parameters
            config = self.base_config.copy()
            for i, key in enumerate(keys):
                setattr(config, key, combo[i])

            # Run backtest
            backtester = SupertrendBacktester(config)
            result = backtester.run_backtest(self.data)

            # Store results with parameters
            results.append({
                'parameters': dict(zip(keys, combo)),
                'total_return_pct': result.total_return_pct,
                'sharpe_ratio': result.sharpe_ratio,
                'max_drawdown_pct': result.max_drawdown_pct,
                'win_rate': result.win_rate,
                'profit_factor': result.profit_factor,
                'num_trades': result.num_trades
            })

            print(f"Tested: {dict(zip(keys, combo))} -> Return: {result.total_return_pct:.2f}%")

        # Sort by return
        results.sort(key=lambda x: x['total_return_pct'], reverse=True)

        return pd.DataFrame(results)

    def parallel_optimize(self, param_grid, n_cores=None):
        """Parallel optimization for faster execution"""
        if n_cores is None:
            n_cores = mp.cpu_count() - 1

        keys = list(param_grid.keys())
        values = list(param_grid.values())
        combinations = list(product(*values))

        # Create partial function
        backtest_func = partial(self._run_single_backtest, keys=keys)

        # Run parallel backtests
        with mp.Pool(n_cores) as pool:
            results = pool.map(backtest_func, combinations)

        # Convert to DataFrame
        return pd.DataFrame(results).sort_values('total_return_pct', ascending=False)

    def _run_single_backtest(self, combo, keys):
        """Run a single backtest with given parameters"""
        config = self.base_config.copy()
        for i, key in enumerate(keys):
            setattr(config, key, combo[i])

        backtester = SupertrendBacktester(config)
        result = backtester.run_backtest(self.data)

        return {
            'parameters': dict(zip(keys, combo)),
            'total_return_pct': result.total_return_pct,
            'sharpe_ratio': result.sharpe_ratio,
            'max_drawdown_pct': result.max_drawdown_pct,
            'win_rate': result.win_rate,
            'profit_factor': result.profit_factor,
            'num_trades': result.num_trades
        }

class BacktestVisualizer:
    """Visualize backtest results"""

    @staticmethod
    def plot_equity_curve(results):
        """Plot equity curve and drawdown"""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

        # Equity curve
        ax1.plot(results.equity_curve.index, results.equity_curve.values, label='Equity Curve')
        ax1.fill_between(results.equity_curve.index, results.equity_curve.values,
                         results.initial_capital, alpha=0.3)
        ax1.set_ylabel('Capital ($)')
        ax1.set_title('Equity Curve')
        ax1.grid(True, alpha=0.3)
        ax1.legend()

        # Drawdown
        cummax = results.equity_curve.cummax()
        drawdown = (results.equity_curve - cummax) / cummax * 100
        ax2.fill_between(drawdown.index, drawdown.values, 0, color='red', alpha=0.3)
        ax2.set_ylabel('Drawdown (%)')
        ax2.set_xlabel('Date')
        ax2.set_title('Drawdown')
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()

    @staticmethod
    def plot_trade_distribution(results):
        """Plot trade PnL distribution"""
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))

        # PnL distribution
        pnls = [t.pnl for t in results.trades]
        axes[0].hist(pnls, bins=30, edgecolor='black', alpha=0.7)
        axes[0].axvline(x=0, color='red', linestyle='--')
        axes[0].set_xlabel('PnL ($)')
        axes[0].set_ylabel('Frequency')
        axes[0].set_title('Trade PnL Distribution')

        # Win/Loss pie chart
        sizes = [results.winning_trades, results.losing_trades]
        labels = ['Winning Trades', 'Losing Trades']
        colors = ['green', 'red']
        axes[1].pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%')
        axes[1].set_title('Win/Loss Ratio')

        plt.tight_layout()
        plt.show()

    @staticmethod
    def plot_optimization_heatmap(optimization_results, x_param, y_param, z_metric='total_return_pct'):
        """Plot optimization results as heatmap"""
        # Pivot data for heatmap
        pivot = optimization_results.pivot_table(
            values=z_metric,
            index=y_param,
            columns=x_param,
            aggfunc='mean'
        )

        plt.figure(figsize=(10, 8))
        sns.heatmap(pivot, annot=True, fmt='.1f', cmap='RdYlGn', center=0)
        plt.title(f'{z_metric} Heatmap')
        plt.tight_layout()
        plt.show()

@dataclass
class BacktestConfig:
    """Backtest configuration"""
    # Data parameters
    SYMBOL: str = "BTCUSDT"
    CATEGORY: str = "linear"
    TIMEFRAME: str = "15"
    START_DATE: datetime = datetime(2023, 1, 1)
    END_DATE: datetime = datetime(2024, 1, 1)

    # Strategy parameters
    ST_PERIOD: int = 10
    ST_MULTIPLIER: float = 3.0

    # Risk management
    INITIAL_CAPITAL: float = 10000.0
    RISK_PER_TRADE_PCT: float = 1.0
    MAX_POSITION_SIZE_USD: float = 5000.0
    MIN_POSITION_SIZE_USD: float = 100.0
    STOP_LOSS_PCT: float = 0.015
    TAKE_PROFIT_PCT: float = 0.03

    # Execution
    ALLOW_SHORT: bool = False
    COMMISSION: float = 0.0006

def main():
    """Main backtest execution"""

    # Step 1: Download historical data
    print("Downloading historical data from Bybit...")
    downloader = BybitHistoricalDataDownloader(testnet=False)

    config = BacktestConfig()

    data = downloader.fetch_historical_klines(
        symbol=config.SYMBOL,
        interval=config.TIMEFRAME,
        start_date=config.START_DATE,
        end_date=config.END_DATE,
        category=config.CATEGORY
    )

    # Save data for future use
    downloader.save_to_csv(data, f"{config.SYMBOL}_{config.TIMEFRAME}_backtest.csv")

    print(f"Downloaded {len(data)} bars of data")

    # Step 2: Run initial backtest
    print("\nRunning backtest with default parameters...")
    backtester = SupertrendBacktester(config)
    results = backtester.run_backtest(data)

    # Display results
    print("\n" + "="*60)
    print("BACKTEST RESULTS")
    print("="*60)
    print(f"Initial Capital: ${results.initial_capital:,.2f}")
    print(f"Final Capital: ${results.final_capital:,.2f}")
    print(f"Total Return: ${results.total_return:,.2f} ({results.total_return_pct:.2f}%)")
    print(f"Number of Trades: {results.num_trades}")
    print(f"Winning Trades: {results.winning_trades} ({results.win_rate:.2f}%)")
    print(f"Losing Trades: {results.losing_trades}")
    print(f"Average Win: ${results.avg_win:,.2f}")
    print(f"Average Loss: ${results.avg_loss:,.2f}")
    print(f"Profit Factor: {results.profit_factor:.2f}")
    print(f"Max Drawdown: ${results.max_drawdown:,.2f} ({results.max_drawdown_pct:.2f}%)")
    print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
    print(f"Sortino Ratio: {results.sortino_ratio:.2f}")

    # Step 3: Visualize results
    print("\nGenerating visualizations...")
    visualizer = BacktestVisualizer()
    visualizer.plot_equity_curve(results)
    visualizer.plot_trade_distribution(results)

    # Step 4: Parameter optimization
    print("\nRunning parameter optimization...")
    optimizer = ParameterOptimizer(data, config)

    param_grid = {
        'ST_PERIOD': [7, 10, 14, 20],
        'ST_MULTIPLIER': [2.0, 2.5, 3.0, 3.5],
        'STOP_LOSS_PCT': [0.01, 0.015, 0.02],
        'TAKE_PROFIT_PCT': [0.02, 0.03, 0.04]
    }

    optimization_results = optimizer.optimize_parameters(param_grid)

    # Display top 10 parameter combinations
    print("\nTop 10 Parameter Combinations:")
    print(optimization_results.head(10))

    # Save results
    optimization_results.to_csv('optimization_results.csv', index=False)

    # Step 5: Run backtest with best parameters
    best_params = optimization_results.iloc[0]['parameters'] # Corrected to get the parameters dict
    print(f"\nBest parameters found: {best_params}")

    # Update config with best parameters
    for key, value in best_params.items():
        setattr(config, key, value)

    # Run final backtest
    print("\nRunning backtest with optimized parameters...")
    backtester_optimized = SupertrendBacktester(config)
    results_optimized = backtester_optimized.run_backtest(data)

    print(f"Optimized Return: {results_optimized.total_return_pct:.2f}%")
    print(f"Optimized Sharpe Ratio: {results_optimized.sharpe_ratio:.2f}")
    print(f"Optimized Max Drawdown: {results_optimized.max_drawdown_pct:.2f}%")

    # Export detailed trade log
    trades_df = pd.DataFrame([{ 
        'entry_time': t.entry_time,
        'exit_time': t.exit_time,
        'side': t.side,
        'entry_price': t.entry_price,
        'exit_price': t.exit_price,
        'quantity': t.quantity,
        'pnl': t.pnl,
        'pnl_pct': t.pnl_pct,
        'exit_reason': t.exit_reason
    } for t in results_optimized.trades])

    trades_df.to_csv('backtest_trades.csv', index=False)
    print("\nTrade log saved to 'backtest_trades.csv'")

if __name__ == "__main__":
    main()