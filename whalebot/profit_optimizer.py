import json
import itertools
import re
import asyncio
import os
from pathlib import Path

# Assuming NEON colors are defined in bbwb.py or a common utility file
# For this script, we'll define them locally for clarity, or import if available
# from bbwb import NEON_GREEN, NEON_YELLOW, NEON_RED, NEON_BLUE, NEON_CYAN, NEON_PURPLE, RESET
# For now, let's define them simply for this optimizer script's output
NEON_GREEN = "\033[92m"
NEON_YELLOW = "\033[93m"
NEON_RED = "\033[91m"
NEON_BLUE = "\033[94m"
NEON_CYAN = "\033[96m"
NEON_PURPLE = "\033[95m"
RESET = "\033[0m"

CONFIG_FILE_PATH = "/data/data/com.termux/files/home/Algobots/whalebot/config.json"
BACKTESTER_SCRIPT_PATH = "/data/data/com.termux/files/home/Algobots/whalebot/backtester.py"

async def run_optimization():
    print(f"{NEON_BLUE}--- Starting Profit Optimization ---{RESET}")

    # 1. Load the config.json
    try:
        with open(CONFIG_FILE_PATH, 'r') as f:
            original_config = json.load(f)
    except FileNotFoundError:
        print(f"{NEON_RED}Error: config.json not found at {CONFIG_FILE_PATH}{RESET}")
        return
    except json.JSONDecodeError:
        print(f"{NEON_RED}Error: Invalid JSON in config.json at {CONFIG_FILE_PATH}{RESET}")
        return

    # Define parameter ranges for optimization
    # These ranges should be carefully chosen based on understanding of the strategy
    signal_score_thresholds = [0.7, 0.8, 0.9]
    stop_loss_atr_multiples = [0.4, 0.5, 0.6]
    take_profit_atr_multiples = [0.7, 0.8, 0.9]

    best_pnl = -float('inf')
    best_params = {}
    total_combinations = (len(signal_score_thresholds) *
                         len(stop_loss_atr_multiples) *
                         len(take_profit_atr_multiples))
    current_combination_num = 0

    print(f"{NEON_CYAN}Total combinations to test: {total_combinations}{RESET}")

    # Iterate through all combinations of parameters
    param_combinations = itertools.product(
        signal_score_thresholds,
        stop_loss_atr_multiples,
        take_profit_atr_multiples
    )

    for sst, sl_atr, tp_atr in param_combinations:
        current_combination_num += 1
        print(f"\n{NEON_BLUE}--- Testing Combination {current_combination_num}/{total_combinations} ---{RESET}")
        print(f"{NEON_CYAN}  signal_score_threshold: {sst}{RESET}")
        print(f"{NEON_CYAN}  stop_loss_atr_multiple: {sl_atr}{RESET}")
        print(f"{NEON_CYAN}  take_profit_atr_multiple: {tp_atr}{RESET}")

        # Create a temporary config for the current iteration
        temp_config = original_config.copy()
        temp_config["signal_score_threshold"] = sst
        temp_config["trade_management"]["stop_loss_atr_multiple"] = sl_atr
        temp_config["trade_management"]["take_profit_atr_multiple"] = tp_atr

        # Write the modified config to config.json
        try:
            with open(CONFIG_FILE_PATH, 'w') as f:
                json.dump(temp_config, f, indent=4)
            print(f"{NEON_YELLOW}Updated config.json for current test.{RESET}")
        except IOError as e:
            print(f"{NEON_RED}Error writing to config.json: {e}{RESET}")
            continue

        # Run backtester.py as a subprocess
        process = await asyncio.create_subprocess_exec(
            'python', BACKTESTER_SCRIPT_PATH,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        stdout_str = stdout.decode().strip()
        stderr_str = stderr.decode().strip()

        if process.returncode != 0:
            print(f"{NEON_RED}Backtester exited with error code {process.returncode}{RESET}")
            print(f"{NEON_RED}Stderr: {stderr_str}{RESET}")
            current_pnl = -float('inf') # Treat errors as worst performance
        else:
            # Parse the output to extract total_pnl
            pnl_match = re.search(r"Total PnL: ([-+]?\d+\.?\d*)", stdout_str)
            if pnl_match:
                current_pnl = float(pnl_match.group(1))
                print(f"{NEON_GREEN}Backtest PnL: {current_pnl:.2f}{RESET}")
            else:
                print(f"{NEON_RED}Could not find Total PnL in backtester output.{RESET}")
                print(f"{NEON_YELLOW}Backtester Output:\n{stdout_str}{RESET}")
                current_pnl = -float('inf')

        # Compare and update best performance
        if current_pnl > best_pnl:
            best_pnl = current_pnl
            best_params = {
                "signal_score_threshold": sst,
                "stop_loss_atr_multiple": sl_atr,
                "take_profit_atr_multiple": tp_atr
            }
            print(f"{NEON_PURPLE}New best PnL found: {best_pnl:.2f} with params: {best_params}{RESET}")

    # After all combinations are tested, update config.json with the best parameters
    if best_params:
        original_config["signal_score_threshold"] = best_params["signal_score_threshold"]
        original_config["trade_management"]["stop_loss_atr_multiple"] = best_params["stop_loss_atr_multiple"]
        original_config["trade_management"]["take_profit_atr_multiple"] = best_params["take_profit_atr_multiple"]

        try:
            with open(CONFIG_FILE_PATH, 'w') as f:
                json.dump(original_config, f, indent=4)
            print(f"\n{NEON_GREEN}Optimization complete! config.json updated with best parameters:{RESET}")
            print(f"{NEON_GREEN}  Best PnL: {best_pnl:.2f}{RESET}")
            print(f"{NEON_GREEN}  Best Params: {best_params}{RESET}")
        except IOError as e:
            print(f"{NEON_RED}Error writing final config.json: {e}{RESET}")
    else:
        print(f"\n{NEON_YELLOW}Optimization finished, but no profitable parameters were found.{RESET}")

    print(f"{NEON_BLUE}--- Profit Optimization Finished ---{RESET}")

if __name__ == "__main__":
    asyncio.run(run_optimization())
