import asyncio
import logging
import os
import sys
from decimal import Decimal

import optuna

# Add the current directory to the Python path to import marketmaker1.0.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from marketmaker1_0 import (
    BybitMarketMaker,
    Config,
    DynamicSpreadConfig,
    InventoryStrategyConfig,
    StrategyConfig,
)

# Configure logging for the optimizer
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
optimizer_logger = logging.getLogger("ProfitOptimizer")


async def run_simulation_for_trial(
    trial_config: Config, duration_ticks: int = 1000
) -> Decimal:
    """
    Runs a simulation of the market maker bot with the given configuration
    and returns the net realized PnL.
    """
    bot = None
    try:
        # Store original log level
        original_log_level = trial_config.files.log_level

        # Create a new FilesConfig instance with the desired log_level for the trial
        new_files_config = trial_config.files.__class__(
            log_level="WARNING",
            log_file=trial_config.files.log_file,
            state_file=trial_config.files.state_file,
            db_file=trial_config.files.db_file,
        )

        # Reconstruct the Config object with the new FilesConfig and other original attributes
        # This is necessary because Config and its nested dataclasses are frozen
        temp_config = Config(
            api_key=trial_config.api_key,
            api_secret=trial_config.api_secret,
            testnet=trial_config.testnet,
            trading_mode=trial_config.trading_mode,
            symbol=trial_config.symbol,
            category=trial_config.category,
            leverage=trial_config.leverage,
            min_order_value_usd=trial_config.min_order_value_usd,
            max_order_size_pct=trial_config.max_order_size_pct,
            max_net_exposure_usd=trial_config.max_net_exposure_usd,
            order_type=trial_config.order_type,
            time_in_force=trial_config.time_in_force,
            post_only=trial_config.post_only,
            strategy=trial_config.strategy,
            system=trial_config.system,
            files=new_files_config,
            initial_dry_run_capital=trial_config.initial_dry_run_capital,
        )

        bot = BybitMarketMaker(temp_config)

        # Initialize bot without connecting real websockets
        await bot._initialize_bot()

        # Run the main loop for a fixed number of ticks
        for _ in range(duration_ticks):
            await bot._main_loop_tick()
            await asyncio.sleep(
                trial_config.system.loop_interval_sec
            )  # Simulate time passing

        net_pnl = bot.state.metrics.net_realized_pnl
        optimizer_logger.info(f"Trial finished. Net PnL: {net_pnl:.4f}")
        return net_pnl

    except Exception as e:
        optimizer_logger.error(f"Error during simulation trial: {e}", exc_info=True)
        return Decimal("-999999999")  # Return a very low value for failed trials
    finally:
        if bot:
            # Ensure bot is stopped gracefully and resources are released
            await bot.stop()
            # Restore original log level for the bot's logger if it was changed
            bot.logger.setLevel(getattr(logging, original_log_level.upper()))


def objective(trial: optuna.Trial) -> float:
    """
    Optuna objective function to optimize market maker parameters.
    """
    optimizer_logger.info(f"Starting trial {trial.number}...")

    # Define parameters to optimize
    base_spread_pct = trial.suggest_float("base_spread_pct", 0.0001, 0.005, log=True)
    base_order_size_pct_of_balance = trial.suggest_float(
        "base_order_size_pct_of_balance", 0.001, 0.01
    )
    max_outstanding_orders = trial.suggest_int("max_outstanding_orders", 1, 5)
    min_profit_spread_after_fees_pct = trial.suggest_float(
        "min_profit_spread_after_fees_pct", 0.00001, 0.0005, log=True
    )

    # Dynamic spread parameters
    dynamic_spread_enabled = trial.suggest_categorical(
        "dynamic_spread_enabled", [True, False]
    )
    volatility_multiplier = (
        Decimal(str(trial.suggest_float("volatility_multiplier", 0.5, 5.0)))
        if dynamic_spread_enabled
        else Decimal("0")
    )
    price_change_smoothing_factor = (
        Decimal(str(trial.suggest_float("price_change_smoothing_factor", 0.1, 0.9)))
        if dynamic_spread_enabled
        else Decimal("0")
    )

    # Inventory strategy parameters
    inventory_enabled = trial.suggest_categorical("inventory_enabled", [True, False])
    skew_intensity = (
        Decimal(str(trial.suggest_float("skew_intensity", 0.1, 1.0)))
        if inventory_enabled
        else Decimal("0")
    )
    max_inventory_ratio = (
        Decimal(str(trial.suggest_float("max_inventory_ratio", 0.1, 0.9)))
        if inventory_enabled
        else Decimal("0")
    )

    # Create a Config object with trial parameters
    strategy_config = StrategyConfig(
        base_spread_pct=Decimal(str(base_spread_pct)),
        base_order_size_pct_of_balance=Decimal(str(base_order_size_pct_of_balance)),
        order_stale_threshold_pct=Decimal("0.0005"),  # Keep fixed for now
        min_profit_spread_after_fees_pct=Decimal(str(min_profit_spread_after_fees_pct)),
        max_outstanding_orders=max_outstanding_orders,
        inventory=InventoryStrategyConfig(
            enabled=inventory_enabled,
            skew_intensity=skew_intensity,
            max_inventory_ratio=max_inventory_ratio,
        ),
        dynamic_spread=DynamicSpreadConfig(
            enabled=dynamic_spread_enabled,
            volatility_multiplier=volatility_multiplier,
            price_change_smoothing_factor=price_change_smoothing_factor,
        ),
    )

    # Use a base config and override strategy
    base_config = Config(
        trading_mode="SIMULATION",  # Always run in simulation mode for optimization
        symbol="XLMUSDT",  # Keep fixed for now
        category="linear",  # Keep fixed for now
        leverage=Decimal("1"),  # Keep fixed for now
        min_order_value_usd=Decimal("10"),  # Keep fixed for now
        max_net_exposure_usd=Decimal("500"),  # Keep fixed for now
        strategy=strategy_config,
        initial_dry_run_capital=Decimal("10000"),
    )

    # Run the simulation
    net_pnl = asyncio.run(run_simulation_for_trial(base_config))

    return float(net_pnl)


if __name__ == "__main__":
    # Create an Optuna study
    study = optuna.create_study(
        direction="maximize",
        study_name="market_maker_profit_opt_v2",  # New study name
        storage="sqlite:///market_maker_profit_opt_v2.db",  # New DB file
        load_if_exists=True,
    )

    # Run the optimization
    num_trials = 50  # Number of trials to run
    timeout_seconds = 3600  # Max optimization time in seconds (1 hour)

    optimizer_logger.info(
        f"Starting optimization for {num_trials} trials or {timeout_seconds} seconds."
    )
    study.optimize(objective, n_trials=num_trials, timeout=timeout_seconds)

    optimizer_logger.info("Optimization finished.")
    optimizer_logger.info(
        f"Best trial: {study.best_trial.value:.4f} with params: {study.best_trial.params}"
    )

    # You can save the results to a CSV if needed
    # import pandas as pd
    # df = study.trials_dataframe()
    # df.to_csv("market_maker_profit_opt_results_v2.csv", index=False)
    # optimizer_logger.info("Optimization results saved to market_maker_profit_opt_results_v2.csv")
