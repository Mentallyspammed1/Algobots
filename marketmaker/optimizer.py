import itertools
import logging
from datetime import datetime, timezone

import pandas as pd

from backtest import BacktestParams, MarketMakerBacktester
from config import Config
from market_maker import MarketMaker

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
            # Create a new MarketMaker instance for each backtest run
            bot = MarketMaker()
            # Apply optimized parameters to the bot's config
            for key, value in params.items():
                setattr(bot.config, key, value)

            # Parse dates from config
            start_date = datetime.strptime(bot.config.START_DATE, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            end_date = datetime.strptime(bot.config.END_DATE, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )

            params_for_backtest = BacktestParams(
                symbol=bot.config.SYMBOL,
                category=bot.config.CATEGORY,
                interval=bot.config.INTERVAL,
                start=start_date,
                end=end_date,
                testnet=bot.config.TESTNET,
                maker_fee=bot.config.MAKER_FEE,
                # Assuming SLIPPAGE is used as volume_cap_ratio in backtest
                volume_cap_ratio=bot.config.SLIPPAGE,
            )
            backtester = MarketMakerBacktester(params_for_backtest, cfg=bot.config)
            summary_results = backtester.run()

            # Store results
            if summary_results:
                net_pnl = summary_results.get("net_pnl", 0.0)
                initial_capital = (
                    bot.config.INITIAL_CAPITAL
                )  # Assuming this is always available
                return_pct = (
                    (net_pnl / initial_capital) * 100 if initial_capital != 0 else 0.0
                )

                result = {"params": params, "pnl": net_pnl, "return_pct": return_pct}
                self.results.append(result)
                logger.info(
                    f"Tested params: {params}, PnL: {result['pnl']:.6f}, Return Pct: {result['return_pct']:.2f}"
                )

        self.display_best_results()

    def get_parameter_combinations(self) -> list:
        """Generates all combinations of parameters from the grid."""
        keys, values = zip(*self.parameter_grid.items(), strict=False)
        return [dict(zip(keys, v, strict=False)) for v in itertools.product(*values)]

    def create_config_from_params(self, params: dict) -> Config:  # Added params: dict
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
        best_pnl_result = results_df.loc[results_df["pnl"].idxmax()]
        best_return_pct_result = results_df.loc[
            results_df["return_pct"].idxmax()
        ]  # Changed from sharpe_ratio

        print("\n" + "=" * 50)
        print("OPTIMIZATION RESULTS")
        print("=" * 50)
        print("Best PnL:")
        print(best_pnl_result)
        print("\nBest Return Pct:")  # Changed from Sharpe Ratio
        print(best_return_pct_result)
        print("=" * 50 + "\n")


if __name__ == "__main__":
    parameter_grid = {
        "BASE_SPREAD": [0.001, 0.002, 0.003, 0.004, 0.005],
        "ORDER_LEVELS": [3, 5, 7, 10],
        "VOLATILITY_WINDOW": [10, 20, 30, 40, 50],
    }

    optimizer = Optimizer(parameter_grid=parameter_grid)
    optimizer.run_optimization()
