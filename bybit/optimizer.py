import copy
import itertools
from decimal import Decimal

# Import the necessary components from our backtester script
from backtester import Backtester, load_config, load_historical_data


def run_optimizer():
    """Runs the optimization process to find the best strategy parameters."""
    print("Starting strategy optimization...")

    # --- Define Parameter Ranges to Test ---
    # Note: Keep these ranges small initially, as the number of combinations grows quickly.
    param_grid = {
        "SPREAD_PERCENTAGE": [Decimal("0.001"), Decimal("0.002"), Decimal("0.003")],
        "PROFIT_PERCENTAGE": [Decimal("0.002"), Decimal("0.004"), Decimal("0.006")],
        "STOP_LOSS_PERCENTAGE": [Decimal("0.005"), Decimal("0.01"), Decimal("0.015")]
    }

    # Load base configuration and data once
    base_config = load_config()
    if not base_config:
        return

    historical_data = load_historical_data()
    if not historical_data:
        print("Cannot run optimizer without historical data.")
        return

    # Create all possible combinations of parameters
    keys, values = zip(*param_grid.items(), strict=False)
    parameter_combinations = [dict(zip(keys, v, strict=False)) for v in itertools.product(*values)]

    total_combinations = len(parameter_combinations)
    print(f"Will test {total_combinations} parameter combinations...")

    best_pnl = Decimal("-Infinity")
    best_params = None

    # --- Run Backtest for Each Combination ---
    for i, params in enumerate(parameter_combinations):
        print(f"Running test {i + 1}/{total_combinations}: {params}")

        # Create a temporary config for this run
        temp_config = copy.deepcopy(base_config)
        for key, value in params.items():
            temp_config[key] = str(value) # Config values are strings

        # Run the backtest with these parameters
        backtester = Backtester(temp_config)
        backtester.run_simulation(historical_data)

        # We don't need the full report here, just the final PnL
        final_balance = backtester.current_balance
        initial_balance = backtester.initial_balance
        pnl = final_balance - initial_balance

        print(f"Resulting PnL: {pnl:.2f} USDT")

        # Check if this is the best result so far
        if pnl > best_pnl:
            best_pnl = pnl
            best_params = params

    # --- Print the Final Report ---
    if best_params:
        print("\n--- Optimization Complete ---")
        print(f"Best PnL found: {best_pnl:.2f} USDT")
        print("Best Parameters:")
        for key, value in best_params.items():
            print(f"  {key}: {value}")
        print("\nTo use these settings, update your config.json file.")
    else:
        print("\n--- Optimization Complete ---")
        print("Could not determine a best parameter set. All runs may have resulted in a loss.")

if __name__ == '__main__':
    run_optimizer()
