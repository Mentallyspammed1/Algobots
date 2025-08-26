import asyncio
import logging
import optuna
from decimal import Decimal
import sys
import os
from dataclasses import replace, asdict
import json

# Add the current directory to the Python path to import marketmaker1_0.py
# This assumes marketmaker1_0.py is in the same directory as this optimizer script.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import all necessary classes from marketmaker1_0.py
from marketmaker1_0 import (
    Config, BybitMarketMaker, StrategyConfig, InventoryStrategyConfig,
    DynamicSpreadConfig, FilesConfig, SystemConfig, ConfigurationError
)

# Configure logging for the optimizer
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
optimizer_logger = logging.getLogger('ProfitOptimizer')
optimizer_logger.setLevel(logging.INFO) # Ensure optimizer logger is INFO level

def create_trial_config(base_config: Config, trial_params: dict) -> Config:
    """
    Creates a new Config object by replacing strategy-related parameters
    from the base_config with values suggested by an Optuna trial.
    Handles nested frozen dataclasses.
    """
    # Extract strategy parameters from trial_params.
    # We pop them to ensure all parameters are used and to avoid passing unused ones.
    base_spread_pct = trial_params.pop("base_spread_pct")
    base_order_size_pct_of_balance = trial_params.pop("base_order_size_pct_of_balance")
    max_outstanding_orders = trial_params.pop("max_outstanding_orders")
    min_profit_spread_after_fees_pct = trial_params.pop("min_profit_spread_after_fees_pct")

    dynamic_spread_enabled = trial_params.pop("dynamic_spread_enabled")
    volatility_multiplier = trial_params.pop("volatility_multiplier")
    price_change_smoothing_factor = trial_params.pop("price_change_smoothing_factor")

    inventory_enabled = trial_params.pop("inventory_enabled")
    skew_intensity = trial_params.pop("skew_intensity")
    max_inventory_ratio = trial_params.pop("max_inventory_ratio")

    # Create new nested dataclass instances for InventoryStrategyConfig
    new_inventory_config = replace(
        base_config.strategy.inventory, # Start with base inventory config
        enabled=inventory_enabled,
        skew_intensity=Decimal(str(skew_intensity)),
        max_inventory_ratio=Decimal(str(max_inventory_ratio))
    )

    # Create new nested dataclass instances for DynamicSpreadConfig
    new_dynamic_spread_config = replace(
        base_config.strategy.dynamic_spread, # Start with base dynamic spread config
        enabled=dynamic_spread_enabled,
        volatility_multiplier=Decimal(str(volatility_multiplier)),
        price_change_smoothing_factor=Decimal(str(price_change_smoothing_factor))
    )

    # Create a new StrategyConfig instance with all updated nested configs and direct parameters
    new_strategy_config = replace(
        base_config.strategy, # Start with base strategy config
        base_spread_pct=Decimal(str(base_spread_pct)),
        base_order_size_pct_of_balance=Decimal(str(base_order_size_pct_of_balance)),
        max_outstanding_orders=max_outstanding_orders,
        min_profit_spread_after_fees_pct=Decimal(str(min_profit_spread_after_fees_pct)),
        inventory=new_inventory_config,
        dynamic_spread=new_dynamic_spread_config
    )

    # Create a new FilesConfig instance to suppress verbose bot logging during trials
    new_files_config = replace(
        base_config.files,
        log_level="WARNING"
    )
    
    # Finally, create the complete new Config object with the updated strategy and file settings.
    # Ensure trading_mode is always SIMULATION for optimization.
    new_config = replace(
        base_config,
        strategy=new_strategy_config,
        files=new_files_config,
        trading_mode="SIMULATION"
    )
    
    return new_config


async def run_simulation_for_trial(trial_config: Config, duration_ticks: int = 2000) -> Decimal:
    """
    Runs a simulation of the market maker bot with the given configuration
    and returns the net realized PnL.
    
    Args:
        trial_config: The Config object for the current trial.
        duration_ticks: Number of main loop iterations to run the simulation.
                        Each tick simulates `trial_config.system.loop_interval_sec` period.
                        Increased from 1000 to 2000 for longer simulation to allow more trades.
    Returns:
        The net realized PnL as Decimal. Returns Decimal('-inf') if an error occurs.
    """
    bot = None
    try:
        # Initialize the bot with the trial-specific configuration
        bot = BybitMarketMaker(trial_config)
        
        # Initialize bot without connecting real websockets (as it's SIMULATION mode)
        await bot._initialize_bot()

        # Run the main loop for a fixed number of ticks
        for i in range(duration_ticks):
            # In SIMULATION mode, _main_loop_tick internally handles price updates
            # via a simple random walk and simulates order fills.
            await bot._main_loop_tick()
            
            # Simulate the passage of time. This is crucial for features like
            # order stale checks, circuit breakers, and price history tracking.
            await asyncio.sleep(trial_config.system.loop_interval_sec)

            # Optional: Log simulation progress for long-running trials
            if (i + 1) % (duration_ticks // 10) == 0:
                optimizer_logger.debug(f"  Simulating tick {i+1}/{duration_ticks} for trial. Current PnL: {bot.state.metrics.net_realized_pnl:.4f}")

        net_pnl = bot.state.metrics.net_realized_pnl
        optimizer_logger.info(f"  Simulation finished. Net Realized PnL: {net_pnl:.4f}")
        return net_pnl

    except ConfigurationError as e:
        # Catch specific configuration errors which indicate an invalid parameter set
        optimizer_logger.error(f"  Configuration error during simulation trial: {e}. Returning -infinity.", exc_info=False)
        return Decimal('-inf')
    except Exception as e:
        # Catch any other unexpected errors during the simulation
        optimizer_logger.error(f"  Unhandled error during simulation trial: {e}. Returning -infinity.", exc_info=True)
        return Decimal('-inf')
    finally:
        if bot:
            # Ensure bot resources are released gracefully, regardless of simulation outcome
            await bot.stop() # This method calls _shutdown_bot, which closes DB, clears state etc.


def objective(trial: optuna.Trial) -> float:
    """
    Optuna objective function for hyperparameter optimization.
    It runs a market maker bot simulation with trial-specific parameters
    and returns the resulting net realized PnL to be maximized.
    """
    optimizer_logger.info(f"Starting Optuna trial {trial.number}...")

    # --- Define parameters to optimize with refined ranges and steps ---

    # Base strategy parameters
    base_spread_pct = trial.suggest_float(
        "base_spread_pct", 0.0001, 0.005, log=True,
        help="Base bid/ask spread as a percentage of mid-price (e.g., 0.001 = 0.1%)"
    ) # Range: 0.01% to 0.5%
    base_order_size_pct_of_balance = trial.suggest_float(
        "base_order_size_pct_of_balance", 0.001, 0.02, step=0.001,
        help="Base order size as a percentage of available capital (e.g., 0.005 = 0.5%)"
    ) # Range: 0.1% to 2.0%, step 0.1%
    max_outstanding_orders = trial.suggest_int(
        "max_outstanding_orders", 1, 10,
        help="Maximum number of outstanding orders on each side (bid/ask)"
    ) # Range: 1 to 10 orders
    min_profit_spread_after_fees_pct = trial.suggest_float(
        "min_profit_spread_after_fees_pct", 0.00001, 0.0005, log=True,
        help="Minimum required profit spread (after maker fees) as a percentage"
    ) # Range: 0.001% to 0.05%

    # Dynamic spread parameters
    dynamic_spread_enabled = trial.suggest_categorical(
        "dynamic_spread_enabled", [True, False],
        help="Enable/disable dynamic spread adjustment based on volatility"
    )
    # Volatility multiplier and smoothing factor are only relevant if dynamic spread is enabled
    volatility_multiplier = trial.suggest_float(
        "volatility_multiplier", 0.1, 5.0,
        help="Multiplier for volatility when calculating dynamic spread adjustment"
    ) if dynamic_spread_enabled else 0.0 # Set to 0 if disabled
    price_change_smoothing_factor = trial.suggest_float(
        "price_change_smoothing_factor", 0.1, 0.9, step=0.1,
        help="Smoothing factor for EMA of price changes (0.1 for fast, 0.9 for slow)"
    ) if dynamic_spread_enabled else 0.0 # Set to 0 if disabled

    # Inventory strategy parameters
    inventory_enabled = trial.suggest_categorical(
        "inventory_enabled", [True, False],
        help="Enable/disable inventory skewing to balance position"
    )
    # Skew intensity and max inventory ratio are only relevant if inventory strategy is enabled
    skew_intensity = trial.suggest_float(
        "skew_intensity", 0.1, 2.0,
        help="Intensity of inventory skewing (higher means stronger skew)"
    ) if inventory_enabled else 0.0 # Set to 0 if disabled
    max_inventory_ratio = trial.suggest_float(
        "max_inventory_ratio", 0.05, 0.95, step=0.05,
        help="Maximum desired inventory ratio (e.g., 0.5 = 50% of capital)"
    ) if inventory_enabled else 0.0 # Set to 0 if disabled

    # Create a dictionary of all trial parameters to pass to the helper function
    trial_params = {
        "base_spread_pct": base_spread_pct,
        "base_order_size_pct_of_balance": base_order_size_pct_of_balance,
        "max_outstanding_orders": max_outstanding_orders,
        "min_profit_spread_after_fees_pct": min_profit_spread_after_fees_pct,
        "dynamic_spread_enabled": dynamic_spread_enabled,
        "volatility_multiplier": volatility_multiplier,
        "price_change_smoothing_factor": price_change_smoothing_factor,
        "inventory_enabled": inventory_enabled,
        "skew_intensity": skew_intensity,
        "max_inventory_ratio": max_inventory_ratio,
    }

    # Define a base configuration for the bot.
    # We will only override strategy parameters using create_trial_config.
    # Other parameters (API keys, symbol, leverage, etc.) remain constant for all trials.
    # It's important to set a realistic initial_dry_run_capital for simulation.
    base_config = Config(
        api_key="SIM_KEY", # Dummy API key for simulation mode
        api_secret="SIM_SECRET", # Dummy API secret for simulation mode
        testnet=False, # Simulation mode does not interact with Bybit, so testnet setting is irrelevant
        trading_mode="SIMULATION", # Ensure we are always in simulation mode for optimization
        symbol="XLMUSDT", # Example symbol; keep consistent for meaningful optimization
        category="linear", # Example category; keep consistent
        leverage=Decimal('1'), # For simplicity in simulation, use 1x leverage
        min_order_value_usd=Decimal('10'), # Minimum order value
        max_order_size_pct=Decimal('0.1'), # Max individual order size as % of balance
        max_net_exposure_usd=Decimal('1000'), # Max total exposure in USD
        order_type="Limit",
        time_in_force="GTC",
        post_only=True,
        # Provide a default StrategyConfig which will be fully replaced by trial parameters
        strategy=StrategyConfig(), 
        # Keep system loop interval consistent for comparable simulations
        system=SystemConfig(loop_interval_sec=1), 
        # Configure file logging for the optimizer (bot's log level will be WARNING)
        files=FilesConfig(
            log_level="INFO", 
            log_file="optimizer_bot.log",
            state_file="optimizer_bot_state.pkl",
            db_file="optimizer_bot_data.db"
        ),
        initial_dry_run_capital=Decimal('10000') # Starting capital for the simulation
    )

    # Create the trial-specific configuration by merging base_config with trial_params
    trial_config = create_trial_config(base_config, trial_params)

    # Run the simulation with the generated trial configuration
    net_pnl = asyncio.run(run_simulation_for_trial(trial_config))
    
    # Optuna aims to maximize the objective function, so we return the net realized PnL
    return float(net_pnl)

if __name__ == "__main__":
    # --- Pre-check: Ensure the market maker bot's code file exists ---
    market_maker_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "marketmaker1_0.py")
    if not os.path.exists(market_maker_file):
        optimizer_logger.error(f"Error: Required file '{market_maker_file}' not found.")
        optimizer_logger.error("Please ensure the market maker bot's code is saved as 'marketmaker1_0.py' in the same directory.")
        sys.exit(1)

    # --- Optuna Study Setup ---
    # Define a unique name for the study and its storage database
    study_name = "market_maker_profit_opt_v3" 
    storage_path = f"sqlite:///{study_name}.db"

    optimizer_logger.info(f"Creating/Loading Optuna study: '{study_name}' from '{storage_path}'")
    # Create or load an existing Optuna study.
    # `load_if_exists=True` allows resuming optimization from a previous run.
    study = optuna.create_study(
        direction="maximize", # We aim to maximize the Net Realized PnL
        study_name=study_name,
        storage=storage_path,
        load_if_exists=True 
    )

    # --- Optimization Parameters ---
    num_trials = 100 # Number of new trials to run in this optimization session
    timeout_seconds = 7200 # Maximum optimization time in seconds (e.g., 7200s = 2 hours)
    
    optimizer_logger.info(f"Starting optimization for {num_trials} new trials or {timeout_seconds} seconds.")
    optimizer_logger.info("This process will run multiple bot simulations sequentially and might take significant time.")
    optimizer_logger.info("Intermediate results and study state are saved to the SQLite database.")

    # --- Run Optimization ---
    try:
        study.optimize(objective, n_trials=num_trials, timeout=timeout_seconds)
    except KeyboardInterrupt:
        optimizer_logger.info("Optimization interrupted by user (KeyboardInterrupt).")
    except Exception as e:
        optimizer_logger.error(f"An unexpected error occurred during optimization: {e}", exc_info=True)

    optimizer_logger.info("\nOptimization finished.")

    # --- Report Best Results ---
    if study.best_trial:
        optimizer_logger.info(f"Best trial found: Trial {study.best_trial.number}")
        optimizer_logger.info(f"  Value (Maximized Net Realized PnL): {study.best_trial.value:.4f}")
        optimizer_logger.info("  Best parameters:")
        for key, value in study.best_trial.params.items():
            optimizer_logger.info(f"    {key}: {value}")

        # --- Save Best Parameters to JSON ---
        best_params_file = "best_market_maker_params.json"
        try:
            # Convert Decimal values to string for proper JSON serialization
            serializable_params = {k: str(v) if isinstance(v, Decimal) else v for k, v in study.best_trial.params.items()}
            with open(best_params_file, "w") as f:
                json.dump(serializable_params, f, indent=4)
            optimizer_logger.info(f"Best parameters saved to '{best_params_file}'.")
            optimizer_logger.info("You can use these parameters to update your bot's configuration for live trading.")
        except Exception as e:
            optimizer_logger.error(f"Failed to save best parameters to JSON file: {e}", exc_info=True)
    else:
        optimizer_logger.warning("No successful trials completed to determine best parameters.")

    # --- Optional: Save all trial results to CSV ---
    # Requires pandas: `pip install pandas`
    # try:
    #     import pandas as pd
    #     df = study.trials_dataframe()
    #     csv_file = f"{study_name}_results.csv"
    #     df.to_csv(csv_file, index=False)
    #     optimizer_logger.info(f"All optimization results saved to '{csv_file}'.")
    # except ImportError:
    #     optimizer_logger.warning("Pandas not installed. Cannot save trials to CSV. Install with 'pip install pandas'.")
    # except Exception as e:
    #     optimizer_logger.error(f"Failed to save trials dataframe to CSV: {e}", exc_info=True)
