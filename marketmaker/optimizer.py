import itertools
import logging
import pandas as pd
import argparse
from config import Config
from backtester import BacktestEngine
from market_maker import MarketMaker
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Optimizer:
    def __init__(self, parameter_grid: dict):
        self.parameter_grid = parameter_grid
        self.results = []

    def run_optimization(self):
        """Runs the optimization process."""
        logger.info("Starting optimization...")

        param_combinations = self.get_parameter_combinations()

        for params in param_combinations:
            config = self.create_config_from_params(params)
            market_maker = MarketMaker()
            market_maker.config = config
            market_maker.session = None # Disable live trading

            backtester = BacktestEngine(market_maker, config)
            results = asyncio.run(backtester.run_backtest())
            
            # Store results
            if results:
                result = {
                    'params': params,
                    'pnl': results['total_pnl'],
                    'sharpe_ratio': results['sharpe_ratio']
                }
                self.results.append(result)
                logger.info(f"Tested params: {params}, PnL: {result['pnl']:.2f}, Sharpe Ratio: {result['sharpe_ratio']:.2f}")

        self.display_best_results()

    def get_parameter_combinations(self) -> list:
        """Generates all combinations of parameters from the grid."""
        keys, values = zip(*self.parameter_grid.items())
        return [dict(zip(keys, v)) for v in itertools.product(*values)]

    def create_config_from_params(self, params: dict) -> Config:
        """Creates a Config object from a dictionary of parameters."""
        config = Config()
        for key, value in params.items():
            setattr(config, key, value)
        return config

    def display_best_results(self):
        """Displays the best performing parameter set."""
        if not self.results:
            logger.info("No results to display.")
            return

        results_df = pd.DataFrame(self.results)
        best_pnl_result = results_df.loc[results_df['pnl'].idxmax()]

        print("\n" + "="*50)
        print("OPTIMIZATION RESULTS")
        print("="*50)
        print("Best PnL:")
        print(best_pnl_result)
        print("="*50 + "\n")

if __name__ == '__main__':
    parameter_grid = {
        'BASE_SPREAD': [0.001, 0.002, 0.003, 0.004, 0.005],
        'ORDER_LEVELS': [3, 5, 7, 10],
        'VOLATILITY_WINDOW': [10, 20, 30, 40, 50]
    }

    optimizer = Optimizer(parameter_grid=parameter_grid)
    optimizer.run_optimization()