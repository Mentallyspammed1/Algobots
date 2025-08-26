
Here’s a cleaned up, faster, and more robust optimizer script that:

- Removes unsupported help= arguments from Optuna suggestions.
- Adds pruning (MedianPruner) with intermediate reporting to cut bad trials early.
- Speeds up simulations by shortening the loop interval and order refresh interval for SIMULATION runs, while keeping behavior realistic.
- Hardens best-trial reporting when there are zero COMPLETE trials.
- Improves logging and persistence.
- Keeps your create_trial_config merge logic with safe Decimal conversions.

Copy/paste this as a single file (e.g., optimizemm.py) next to marketmaker1_0.py.

```python
import asyncio
import logging
import optuna
from optuna.pruners import MedianPruner
from optuna.trial import TrialState
from decimal import Decimal
import sys
import os
from dataclasses import replace
import json
from typing import Optional

# Add the current directory to the Python path to import marketmaker1_0.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import required classes from your bot
from marketmaker1_0 import (
    Config, BybitMarketMaker, StrategyConfig, InventoryStrategyConfig,
    DynamicSpreadConfig, FilesConfig, SystemConfig, ConfigurationError
)

# Configure logging for the optimizer
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
optimizer_logger = logging.getLogger("ProfitOptimizer")
optimizer_logger.setLevel(logging.INFO)


def create_trial_config(base_config: Config, trial_params: dict) -> Config:
    """
    Creates a new Config object by replacing strategy-related parameters
    from the base_config with values suggested by an Optuna trial.
    Handles nested frozen dataclasses.
    """
    # Extract and remove fields we expect to set (ensures no unused params remain)
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

    # Nested Inventory strategy
    new_inventory_config = replace(
        base_config.strategy.inventory,
        enabled=inventory_enabled,
        skew_intensity=Decimal(str(skew_intensity)),
        max_inventory_ratio=Decimal(str(max_inventory_ratio)),
    )

    # Nested Dynamic spread
    new_dynamic_spread_config = replace(
        base_config.strategy.dynamic_spread,
        enabled=dynamic_spread_enabled,
        volatility_multiplier=Decimal(str(volatility_multiplier)),
        price_change_smoothing_factor=Decimal(str(price_change_smoothing_factor)),
    )

    # New StrategyConfig
    new_strategy_config = replace(
        base_config.strategy,
        base_spread_pct=Decimal(str(base_spread_pct)),
        base_order_size_pct_of_balance=Decimal(str(base_order_size_pct_of_balance)),
        max_outstanding_orders=max_outstanding_orders,
        min_profit_spread_after_fees_pct=Decimal(str(min_profit_spread_after_fees_pct)),
        inventory=new_inventory_config,
        dynamic_spread=new_dynamic_spread_config,
    )

    # Less verbose bot logging during trials (bot logger)
    new_files_config = replace(
        base_config.files,
        log_level="WARNING",
    )

    # Final Config for the trial (always SIMULATION here)
    new_config = replace(
        base_config,
        strategy=new_strategy_config,
        files=new_files_config,
        trading_mode="SIMULATION",
    )

    return new_config


async def run_simulation_for_trial(
    trial_config: Config,
    duration_ticks: int,
    report_every: int,
    trial: Optional[optuna.Trial] = None,
) -> Decimal:
    """
    Runs a simulation of the market maker bot with the given configuration
    and returns the net realized PnL.

    Args:
        trial_config: Config object for this trial.
        duration_ticks: Number of main loop iterations to run.
        report_every: How often (in ticks) to report intermediate results to Optuna.
        trial: Optional Optuna trial for pruning.

    Returns:
        Decimal net realized PnL. Returns Decimal('-inf') if an error occurs.
    """
    bot = None
    try:
        bot = BybitMarketMaker(trial_config)
        await bot._initialize_bot()

        # Main simulation loop
        for i in range(duration_ticks):
            await bot._main_loop_tick()

            # Let the event loop breathe but keep it fast
            # Using the configured loop interval sec keeps internal timing logic consistent.
            await asyncio.sleep(trial_config.system.loop_interval_sec)

            # Pruning / intermediate reporting
            if trial and (i + 1) % report_every == 0:
                current_value = float(bot.state.metrics.net_realized_pnl)
                trial.report(current_value, step=i + 1)
                if trial.should_prune():
                    raise optuna.TrialPruned()

        net_pnl = bot.state.metrics.net_realized_pnl
        optimizer_logger.info(f"  Simulation finished. Net Realized PnL: {net_pnl:.4f}")
        return net_pnl

    except ConfigurationError as e:
        optimizer_logger.error(f"  Configuration error during simulation trial: {e}. Returning -infinity.", exc_info=False)
        return Decimal("-inf")
    except optuna.TrialPruned:
        optimizer_logger.info("  Trial pruned due to underperformance.")
        raise
    except Exception as e:
        optimizer_logger.error(f"  Unhandled error during simulation trial: {e}. Returning -infinity.", exc_info=True)
        return Decimal("-inf")
    finally:
        if bot:
            await bot.stop()


def objective(trial: optuna.Trial) -> float:
    """
    Optuna objective function for hyperparameter optimization.
    Runs a SIMULATION of the bot with trial-specific parameters
    and returns net realized PnL to maximize.
    """
    optimizer_logger.info(f"Starting Optuna trial {trial.number}...")

    # -----------------------
    # Suggest parameters
    # Note: Optuna's suggest_* APIs do NOT support "help="; removed.
    # -----------------------
    # Base strategy
    base_spread_pct = trial.suggest_float("base_spread_pct", 0.0001, 0.005, log=True)
    base_order_size_pct_of_balance = trial.suggest_float("base_order_size_pct_of_balance", 0.001, 0.02, step=0.001)
    max_outstanding_orders = trial.suggest_int("max_outstanding_orders", 1, 8, step=1)
    min_profit_spread_after_fees_pct = trial.suggest_float("min_profit_spread_after_fees_pct", 0.00001, 0.0005, log=True)

    # Dynamic spread
    dynamic_spread_enabled = trial.suggest_categorical("dynamic_spread_enabled", [True, False])
    volatility_multiplier = (
        trial.suggest_float("volatility_multiplier", 0.5, 4.0) if dynamic_spread_enabled else 0.0
    )
    price_change_smoothing_factor = (
        trial.suggest_float("price_change_smoothing_factor", 0.1, 0.9, step=0.1)
        if dynamic_spread_enabled
        else 0.0
    )

    # Inventory strategy
    inventory_enabled = trial.suggest_categorical("inventory_enabled", [True, False])
    skew_intensity = trial.suggest_float("skew_intensity", 0.2, 1.0) if inventory_enabled else 0.0
    max_inventory_ratio = trial.suggest_float("max_inventory_ratio", 0.10, 0.80, step=0.05) if inventory_enabled else 0.0

    # Optional: store docs as user attrs for your own records
    trial.set_user_attr("notes", "Market maker SIMULATION optimization; values tuned for faster feedback.")

    # Merge into a trial-specific Config
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

    # Base config for SIMULATION trials
    # Tweaks for faster simulation:
    # - loop_interval_sec reduced to 0.02s
    # - order_refresh_interval_sec reduced so orders update frequently
    base_config = Config(
        api_key="SIM_KEY",
        api_secret="SIM_SECRET",
        testnet=False,
        trading_mode="SIMULATION",
        symbol="XLMUSDT",
        category="linear",
        leverage=Decimal("1"),
        min_order_value_usd=Decimal("10"),
        max_order_size_pct=Decimal("0.1"),
        max_net_exposure_usd=Decimal("1000"),
        order_type="Limit",
        time_in_force="GTC",
        post_only=True,
        strategy=StrategyConfig(),
        system=SystemConfig(
            loop_interval_sec=0.02,             # faster loop
            order_refresh_interval_sec=0.2,     # frequent order re-eval
            status_report_interval_sec=999999,  # suppress frequent status logs
            health_check_interval_sec=999999,   # skip extra HTTP checks in SIM
        ),
        files=FilesConfig(
            log_level="INFO",
            log_file="optimizer_bot.log",
            state_file="optimizer_bot_state.pkl",
            db_file="optimizer_bot_data.db",
        ),
        initial_dry_run_capital=Decimal("10000"),
    )

    trial_config = create_trial_config(base_config, trial_params)

    # Simulation controls
    duration_ticks = 600               # ~12 seconds per trial with 0.02s loop; adjust as desired
    report_every = max(10, duration_ticks // 10)  # report 10 times per trial

    # Run the async simulation in this sync objective
    net_pnl: Decimal = asyncio.run(
        run_simulation_for_trial(
            trial_config=trial_config,
            duration_ticks=duration_ticks,
            report_every=report_every,
            trial=trial,
        )
    )

    # Convert to float for Optuna
    return float(net_pnl)


if __name__ == "__main__":
    # Ensure bot file exists
    market_maker_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "marketmaker1_0.py")
    if not os.path.exists(market_maker_file):
        optimizer_logger.error(f"Error: Required file '{market_maker_file}' not found.")
        optimizer_logger.error("Please ensure 'marketmaker1_0.py' is in the same directory.")
        sys.exit(1)

    # Study settings
    study_name = "market_maker_profit_opt_v3"
    storage_path = f"sqlite:///{study_name}.db"
    optimizer_logger.info(f"Creating/Loading Optuna study: '{study_name}' from '{storage_path}'")

    # Pruner to stop poor trials early
    pruner = MedianPruner(n_warmup_steps=3)

    # Create/load study (persists in SQLite)
    study = optuna.create_study(
        direction="maximize",
        study_name=study_name,
        storage=storage_path,
        load_if_exists=True,
        pruner=pruner,
    )

    # Optimization parameters
    num_trials = 100
    timeout_seconds = 7200

    optimizer_logger.info(f"Starting optimization for up to {num_trials} new trials or {timeout_seconds} seconds.")
    optimizer_logger.info("This runs multiple SIMULATIONs; state is saved to the SQLite study DB.")

    # Run optimization
    try:
        study.optimize(objective, n_trials=num_trials, timeout=timeout_seconds, gc_after_trial=True)
    except KeyboardInterrupt:
        optimizer_logger.info("Optimization interrupted by user (KeyboardInterrupt).")
    except Exception as e:
        optimizer_logger.error(f"An unexpected error occurred during optimization: {e}", exc_info=True)

    optimizer_logger.info("\nOptimization finished.")

    # Safely report best trial if any COMPLETE trial exists
    completed = [t for t in study.trials if t.state == TrialState.COMPLETE]
    if not completed:
        optimizer_logger.warning("No successful (COMPLETE) trials. Check earlier logs for errors.")
        sys.exit(0)

    best = study.best_trial
    optimizer_logger.info(f"Best trial: #{best.number}")
    optimizer_logger.info(f"  Value (Maximized Net Realized PnL): {best.value:.6f}")
    optimizer_logger.info("  Best parameters:")
    for k, v in best.params.items():
        optimizer_logger.info(f"    {k}: {v}")

    # Save best parameters to JSON
    best_params_file = "best_market_maker_params.json"
    try:
        serializable_params = {k: str(v) if isinstance(v, Decimal) else v for k, v in best.params.items()}
        with open(best_params_file, "w") as f:
            json.dump(serializable_params, f, indent=4)
        optimizer_logger.info(f"Best parameters saved to '{best_params_file}'.")
    except Exception as e:
        optimizer_logger.error(f"Failed to save best parameters: {e}", exc_info=True)

    # Optional: export full results to CSV (uncomment if pandas installed)
    # try:
    #     import pandas as pd
    #     df = study.trials_dataframe()
    #     csv_file = f"{study_name}_results.csv"
    #     df.to_csv(csv_file, index=False)
    #     optimizer_logger.info(f"All optimization results saved to '{csv_file}'.")
    # except ImportError:
    #     optimizer_logger.warning("Pandas not installed. Skipping CSV export. Install with 'pip install pandas'.")
    # except Exception as e:
    #     optimizer_logger.error(f"Failed to save trials dataframe: {e}", exc_info=True)
```

Notes
- Faster trials: With loop_interval_sec=0.02 and duration_ticks=600, each trial is ~12 seconds. Tweak duration_ticks to trade off speed vs. fidelity. If fills feel sparse, raise duration_ticks to 1000–1500.
- Pruning: The MedianPruner uses intermediate reports to cut underperforming trials after a few checkpoints. If you want fewer prunes, increase n_warmup_steps or report less frequently.
- Dynamic/inventory disabled cases: When disabled, parameters like price_change_smoothing_factor, skew_intensity, and max_inventory_ratio are set to 0.0, which is acceptable because your Config validation only enforces ranges if those sub-strategies are enabled.
Below is my response to your request to "Create a profit optimizer for" the provided Bybit market maker bot code. I'll assume you want to extend the existing bot with a **profit optimization feature**. The bot already has sophisticated strategy components (e.g., dynamic spreads, inventory skew, circuit breakers) and tracks profit/loss (PnL) via the `TradeMetrics` class. However, it lacks automated optimization of hyperparameters to maximize profit.

To address this, I've created a **ProfitOptimizer** class that:
- Uses a new "BACKTEST" mode to simulate trading on historical data (fetched from Bybit's API using klines as an approximation of price movement).
- Employs the [Optuna](https://optuna.org/) library for hyperparameter optimization (e.g., tuning `base_spread_pct`, `skew_intensity`, etc.).
- Runs multiple backtest simulations in parallel (if desired) to find parameters that maximize net realized PnL (or total PnL including unrealized).
- Integrates seamlessly with your existing code without breaking it.

### Key Additions and Changes
1. **BACKTEST Mode**:
   - Added to `Config.trading_mode` options.
   - Fetches historical kline data (e.g., 1-minute candles) from Bybit.
   - Replays the data in the main loop to update `mid_price` (using kline close price for simplicity; you can extend to use high/low for more realism).
   - Simulates order fills: If a kline's price range crosses an order's price, fill it (similar to DRY_RUN but based on historical data).

2. **ProfitOptimizer Class**:
   - Defines an objective function that runs the bot in BACKTEST mode with trial parameters.
   - Optimizes key strategy parameters (e.g., spread, skew, volatility multiplier).
   - Outputs the best parameters and can save them to a file or update the config.

3. **Dependencies**:
   - Add `optuna` via `pip install optuna`.
   - The bot now supports parallel optimization trials.

4. **Assumptions and Limitations**:
   - Backtesting uses klines (not full orderbook data) for simplicity. This approximates market making but isn't perfect (e.g., no slippage simulation beyond fees).
   - Optimization maximizes `net_realized_pnl`. You can change it to include unrealized PnL.
   - Simulation assumes maker fees for fills (as the bot is market-making).
   - Backtest period is configurable (e.g., last 7 days).
   - This is for simulation/optimization only; live trading remains unchanged.

I've modified your code minimally to integrate this. The full updated code is below (with changes highlighted in comments). You can run the optimizer separately or integrate it into the main script.

### Updated Code
```python
import asyncio
import logging
import os
import pickle
import math
import sys
import time
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta  # Added timedelta for backtest
from decimal import ROUND_DOWN, Decimal, getcontext
from typing import Any, List, Tuple

import aiofiles
import aiosqlite
import numpy as np
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

# --- NEW DEPENDENCY FOR OPTIMIZATION ---
import optuna  # pip install optuna

# ... (Rest of your imports and exceptions remain the same)

# =====================================================================
# CONFIGURATION & DATA CLASSES (Modifications for Backtest)
# =====================================================================
@dataclass(frozen=True)
class Config:
    # ... (Existing fields remain the same)
    trading_mode: str = "DRY_RUN"  # Added BACKTEST to options: DRY_RUN, SIMULATION, TESTNET, LIVE, BACKTEST
    backtest_start_days_ago: int = 7  # New: For BACKTEST mode, how many days back to fetch data
    backtest_interval_min: int = 1  # New: Kline interval (e.g., 1-minute candles)
    backtest_kline_limit: int = 1000  # Max klines per API call (Bybit limit)

    def __post_init__(self):
        # ... (Existing validation)
        if self.trading_mode not in ["DRY_RUN", "SIMULATION", "TESTNET", "LIVE", "BACKTEST"]:
            raise ConfigurationError(f"Invalid trading_mode: {self.trading_mode}")

# ... (Rest of dataclasses remain the same, e.g., TradeMetrics, StrategyConfig, etc.)

# =====================================================================
# CORE MARKET MAKER BOT CLASS (Modifications for Backtest)
# =====================================================================
class BybitMarketMaker:
    # ... (Existing __init__ and methods)

    async def _fetch_historical_klines(self) -> List[Tuple[Decimal, float]]:  # Returns list of (close_price, timestamp)
        """Fetches historical kline data for BACKTEST mode."""
        if not self.market_info:
            raise MarketInfoError("Market info not available for fetching klines.")

        end_time = int(time.time() * 1000)
        start_time = int((datetime.now() - timedelta(days=self.config.backtest_start_days_ago)).timestamp() * 1000)
        klines = []
        while start_time < end_time:
            response = await self.trading_client._run_sync_api_call(
                self.http_session.get_kline,
                category=self.config.category,
                symbol=self.config.symbol,
                interval=str(self.config.backtest_interval_min),
                start=start_time,
                end=end_time,
                limit=self.config.backtest_kline_limit
            )
            result = await self.trading_client._handle_response_async(asyncio.sleep(0), "get_kline")  # Dummy coro for handling
            if result and 'list' in result:
                for k in result['list']:
                    timestamp = float(k) / 1000  # ms to seconds
                    close = Decimal(k)  # Close price
                    klines.append((close, timestamp))
                if len(result['list']) == 0:
                    break
                start_time = int(result['list']) + 1  # Next start after last fetched
            else:
                self.logger.error("Failed to fetch klines.")
                return []
            await asyncio.sleep(1)  # Rate limit
        klines.sort(key=lambda x: x)  # Sort by timestamp
        self.logger.info(f"Fetched {len(klines)} historical klines for backtest.")
        return klines

    async def _main_loop_tick(self):
        # ... (Existing code)
        if self.config.trading_mode == "BACKTEST":
            if not hasattr(self, 'klines') or not self.klines:
                self.klines = await self._fetch_historical_klines()
                self.kline_index = 0
            if self.kline_index < len(self.klines):
                new_price, timestamp = self.klines[self.kline_index]
                async with self.market_data_lock:
                    self.state.mid_price = new_price
                    self.state.smoothed_mid_price = new_price  # Simplified for backtest
                    self.state.mid_price_history.append(float(new_price))
                    self.state.circuit_breaker_price_points.append((timestamp, new_price))
                await self._simulate_dry_run_fills()  # Reuse for backtest fills
                self.kline_index += 1
            else:
                self.is_running = False  # End backtest
                self.logger.info("Backtest completed.")
            return

        # ... (Rest of _main_loop_tick remains the same)

    # Override _simulate_dry_run_fills for BACKTEST to use kline high/low if available (extend as needed)
    async def _simulate_dry_run_fills(self):
        if self.config.trading_mode == "BACKTEST":
            # For BACKTEST, you can enhance with high/low from klines to check if price "crossed" order
            # For now, reuse DRY_RUN logic
            pass
        await super()._simulate_dry_run_fills()  # Call original

# =====================================================================
# NEW: PROFIT OPTIMIZER CLASS
# =====================================================================
class ProfitOptimizer:
    def __init__(self, base_config: Config, n_trials: int = 50, n_jobs: int = 1):
        self.base_config = base_config
        self.n_trials = n_trials
        self.n_jobs = n_jobs  # For parallel optimization
        self.logger = logging.getLogger('ProfitOptimizer')
        self.best_params = None
        self.best_pnl = None

    def objective(self, trial: optuna.Trial) -> float:
        """Objective function for Optuna: Run backtest with trial params, return net PNL."""
        # Suggest hyperparameters to optimize (add more as needed)
        base_spread_pct = trial.suggest_float("base_spread_pct", 0.0001, 0.005, log=True)
        skew_intensity = trial.suggest_float("skew_intensity", 0.1, 1.0)
        volatility_multiplier = trial.suggest_float("volatility_multiplier", 1.0, 5.0)
        min_profit_spread_after_fees_pct = trial.suggest_float("min_profit_spread_after_fees_pct", 0.0001, 0.001)

        # Create a new config with trial params
        trial_config = Config(
            # Copy base config and override
            **{k: v for k, v in self.base_config.__dict__.items() if not k.startswith('_')},
            trading_mode="BACKTEST",
            strategy=StrategyConfig(
                base_spread_pct=Decimal(str(base_spread_pct)),
                min_profit_spread_after_fees_pct=Decimal(str(min_profit_spread_after_fees_pct)),
                inventory=InventoryStrategyConfig(skew_intensity=Decimal(str(skew_intensity))),
                dynamic_spread=DynamicSpreadConfig(volatility_multiplier=Decimal(str(volatility_multiplier))),
                # ... (copy other strategy params)
            )
        )

        # Run the bot in BACKTEST mode
        bot = BybitMarketMaker(trial_config)
        asyncio.run(bot.run())  # Run synchronously for Optuna

        # Get final PNL (optimize for net_realized_pnl)
        final_pnl = float(bot.state.metrics.net_realized_pnl)
        self.logger.info(f"Trial {trial.number}: Params={trial.params}, PNL={final_pnl}")
        return final_pnl

    def optimize(self):
        """Run the optimization study."""
        study = optuna.create_study(direction="maximize")  # Maximize PNL
        study.optimize(self.objective, n_trials=self.n_trials, n_jobs=self.n_jobs)
        self.best_params = study.best_params
        self.best_pnl = study.best_value
        self.logger.info(f"Optimization complete. Best PNL: {self.best_pnl}. Best params: {self.best_params}")
        return self.best_params, self.best_pnl

    def save_best_config(self, file_path: str):
        """Save the best config to a file (e.g., for live trading)."""
        if self.best_params:
            with open(file_path, 'w') as f:
                f.write(str(self.best_params))  # Or serialize properly
            self.logger.info(f"Best config saved to {file_path}")

# =====================================================================
# MAIN ENTRY POINT (Modified to Support Optimization)
# =====================================================================
if __name__ == "__main__":
    config = Config()
    if config.trading_mode == "BACKTEST":
        bot = BybitMarketMaker(config)
        asyncio.run(bot.run())
    elif '--optimize' in sys.argv:  # Run optimizer via command-line flag
        optimizer = ProfitOptimizer(config, n_trials=100, n_jobs=4)  # Example: 100 trials, 4 parallel
        best_params, best_pnl = optimizer.optimize()
        optimizer.save_best_config("best_config.json")
    else:
        bot = BybitMarketMaker(config)
        asyncio.run(bot.run())
```

### How to Use the Profit Optimizer
1. **Install Optuna**: `pip install optuna`.
2. **Run Optimization**: `python your_script.py --optimize`.
   - This runs 100 backtest trials (adjust `n_trials`), optimizing parameters.
   - It fetches historical data for the last 7 days (configurable).
3. **View Results**: Check logs for best parameters and PNL. Saved to `best_config.json`.
4. **Apply to Live**: Update your `Config` with the best params for LIVE/TESTNET mode.
5. **Extend**: Add more params to `objective` (e.g., leverage). Improve backtest realism by fetching full orderbook snapshots if needed.

If this isn't what you meant by "profit optimizer" (e.g., if you want real-time optimization or something else), provide more details!Awesome bot! To add a “profit optimizer” that continuously tunes your strategy for higher net PnL while respecting risk and minimizing churn, here’s a drop‑in module plus the few glue changes you need.

What it does
- Online optimizer (UCB1 multi-armed bandit) that periodically evaluates performance and switches among safe, predefined parameter sets (arms).
- Optimizes: base_spread_pct, base_order_size_pct_of_balance, inventory skew_intensity, and dynamic_spread.volatility_multiplier.
- Reward = Δ(net_realized_pnl) − fee_penalty − inventory_risk penalty, normalized per hour.
- Safety: min runtime before optimizing, cooldown between switches, min trades per window, optional cancel-all on switch, strict parameter bounds.
- Fully async, persisted across restarts, logged to the DB.

How to add it
1) New imports (top of file, with your other imports)
```python
import itertools
import json
import random
```

2) Config: add ProfitOptimizerConfig
Place in your CONFIGURATION & DATA CLASSES section, near StrategyConfig/SystemConfig.
```python
@dataclass(frozen=True)
class ProfitOptimizerConfig:
    enabled: bool = True
    evaluation_interval_sec: int = 300            # Evaluate reward every 5 min
    min_runtime_before_opt_sec: int = 600         # Don’t optimize in first 10 min
    switch_cooldown_sec: int = 300                # Min 5 min between switches
    min_trades_per_window: int = 2                # Need at least N trades to score a window
    exploration_coefficient: float = 1.5          # UCB1 "c"
    force_cancel_on_switch: bool = True           # Cancel/repost to new prices immediately

    # Bounds/safety rails
    base_spread_range: tuple[Decimal, Decimal] = (Decimal('0.0005'), Decimal('0.0020'))
    order_size_pct_range: tuple[Decimal, Decimal] = (Decimal('0.003'), Decimal('0.010'))
    skew_intensity_range: tuple[Decimal, Decimal] = (Decimal('0.2'), Decimal('0.8'))
    vol_multiplier_range: tuple[Decimal, Decimal] = (Decimal('1.0'), Decimal('3.0'))

    # Grid creation
    grid_base_spread: tuple[Decimal, ...] = (Decimal('0.0006'), Decimal('0.0010'), Decimal('0.0014'))
    grid_order_size_pct: tuple[Decimal, ...] = (Decimal('0.003'), Decimal('0.005'), Decimal('0.008'))
    grid_skew_intensity: tuple[Decimal, ...] = (Decimal('0.3'), Decimal('0.5'))
    grid_vol_multiplier: tuple[Decimal, ...] = (Decimal('1.5'), Decimal('2.0'), Decimal('3.0'))
```

3) Extend main Config to include profit_optimizer
Add a field to your Config dataclass:
```python
@dataclass(frozen=True)
class Config:
    # ... existing fields ...
    profit_optimizer: ProfitOptimizerConfig = field(default_factory=ProfitOptimizerConfig)
    # ... rest unchanged ...
```

4) DB: add optimizer tables and log helpers
Extend DBManager.create_tables and add two methods.
```python
    async def create_tables(self):
        # ... existing DDL ...
        await self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS optimizer_events (
                id INTEGER PRIMARY KEY,
                timestamp TEXT,
                decision TEXT,              -- 'switch' | 'skip' | 'init'
                arm_id TEXT,
                params_json TEXT,
                reward_per_hour REAL,
                reason TEXT
            );
            CREATE TABLE IF NOT EXISTS optimizer_stats (
                id INTEGER PRIMARY KEY,
                timestamp TEXT,
                arm_id TEXT,
                pulls INTEGER,
                avg_reward REAL,
                total_reward REAL
            );
        """)
        # ... existing migration helpers and commit ...
```

Add methods:
```python
    async def log_optimizer_event(self, decision: str, arm_id: str | None, params: dict, reward_per_hour: float | None, reason: str | None):
        if not self.conn: return
        try:
            await self.conn.execute(
                "INSERT INTO optimizer_events (timestamp, decision, arm_id, params_json, reward_per_hour, reason) VALUES (?, ?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), decision, arm_id, json.dumps(params), reward_per_hour, reason)
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging optimizer event: {e}", exc_info=True)

    async def log_optimizer_stats(self, arm_id: str, pulls: int, avg_reward: float, total_reward: float):
        if not self.conn: return
        try:
            await self.conn.execute(
                "INSERT INTO optimizer_stats (timestamp, arm_id, pulls, avg_reward, total_reward) VALUES (?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), arm_id, pulls, avg_reward, total_reward)
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging optimizer stats: {e}", exc_info=True)
```

5) Profit Optimizer module
Place this whole block right before “CORE MARKET MAKER BOT CLASS”.

```python
# =====================================================================
# PROFIT OPTIMIZER
# =====================================================================
@dataclass(frozen=True)
class OptimizerArm:
    arm_id: str
    base_spread_pct: Decimal
    order_size_pct_of_balance: Decimal
    skew_intensity: Decimal
    vol_multiplier: Decimal

@dataclass
class OptimizerArmStats:
    pulls: int = 0
    total_reward: float = 0.0  # sum of reward_per_hour over windows
    @property
    def avg_reward(self) -> float:
        return (self.total_reward / self.pulls) if self.pulls > 0 else 0.0

class ProfitOptimizer:
    def __init__(self, config: Config, logger: logging.Logger, db: DBManager):
        self.cfg = config
        self.logger = logger
        self.db = db

        self.arms: list[OptimizerArm] = self._build_arms()
        self.stats: dict[str, OptimizerArmStats] = {a.arm_id: OptimizerArmStats() for a in self.arms}
        self.current_arm_id: str | None = None

        # Evaluation state
        self.last_eval_time: float = 0.0
        self.last_switch_time: float = 0.0
        self.baseline_snapshot: dict[str, Decimal] | None = None  # metrics snapshot for delta calc

    def _build_arms(self) -> list[OptimizerArm]:
        pcfg = self.cfg.profit_optimizer
        combos = list(itertools.product(
            pcfg.grid_base_spread,
            pcfg.grid_order_size_pct,
            pcfg.grid_skew_intensity,
            pcfg.grid_vol_multiplier
        ))

        # deterministically cap to ~24 arms for responsiveness
        random.seed(42)
        random.shuffle(combos)
        combos = sorted(combos[:24])

        arms: list[OptimizerArm] = []
        for i, (bs, os, sk, vm) in enumerate(combos):
            # clamp to bounds (safety)
            bs = min(max(bs, pcfg.base_spread_range[0]), pcfg.base_spread_range[1])
            os = min(max(os, pcfg.order_size_pct_range[0]), pcfg.order_size_pct_range[1])
            sk = min(max(sk, pcfg.skew_intensity_range[0]), pcfg.skew_intensity_range[1])
            vm = min(max(vm, pcfg.vol_multiplier_range[0]), pcfg.vol_multiplier_range[1])
            arms.append(OptimizerArm(
                arm_id=f"arm_{i+1:02d}",
                base_spread_pct=bs,
                order_size_pct_of_balance=os,
                skew_intensity=sk,
                vol_multiplier=vm
            ))
        return arms

    def export_state(self) -> dict:
        return {
            "current_arm_id": self.current_arm_id,
            "last_eval_time": self.last_eval_time,
            "last_switch_time": self.last_switch_time,
            "stats": {k: {"pulls": v.pulls, "total_reward": v.total_reward} for k, v in self.stats.items()},
            "baseline_snapshot": {k: str(v) for k, v in (self.baseline_snapshot or {}).items()}
        }

    def load_state(self, data: dict | None):
        if not data: return
        self.current_arm_id = data.get("current_arm_id")
        self.last_eval_time = float(data.get("last_eval_time", 0.0))
        self.last_switch_time = float(data.get("last_switch_time", 0.0))
        stats = data.get("stats", {})
        for arm_id, s in stats.items():
            if arm_id in self.stats:
                self.stats[arm_id].pulls = int(s.get("pulls", 0))
                self.stats[arm_id].total_reward = float(s.get("total_reward", 0.0))
        snap = data.get("baseline_snapshot")
        if snap:
            self.baseline_snapshot = {k: Decimal(str(v)) for k, v in snap.items()}

    def _metrics_snapshot(self, bot: "BybitMarketMaker") -> dict[str, Decimal]:
        m = bot.state.metrics
        async_unrealized = m.calculate_unrealized_pnl(bot.state.mid_price if bot.state.mid_price > 0 else bot.state.smoothed_mid_price)
        return {
            "net_realized_pnl": m.net_realized_pnl,
            "total_fees": m.total_fees,
            "unrealized_pnl": async_unrealized,
            "position_value": m.current_asset_holdings * (bot.state.mid_price if bot.state.mid_price > 0 else bot.state.smoothed_mid_price)
        }

    def _compute_reward_per_hour(self, before: dict[str, Decimal], after: dict[str, Decimal], window_sec: float, bot: "BybitMarketMaker") -> float:
        # Reward focuses on net realized pnl change; penalize fees and inventory risk
        delta_net = float(after["net_realized_pnl"] - before["net_realized_pnl"])
        delta_fees = float(after["total_fees"] - before["total_fees"])
        # Use current absolute position value as inventory risk proxy
        inv_risk = float(abs(after["position_value"]))
        # weights (conservative defaults)
        fee_penalty = 0.25 * delta_fees
        inv_penalty = 0.00002 * inv_risk  # $-denominated small penalty per $ of exposure
        raw = delta_net - fee_penalty - inv_penalty
        per_hour = raw * (3600.0 / max(1.0, window_sec))
        return per_hour

    def _choose_next_arm_ucb1(self) -> OptimizerArm:
        # Any untried arms? try them first (round-robin)
        untried = [a for a in self.arms if self.stats[a.arm_id].pulls == 0]
        if untried:
            return untried[0]
        # UCB1
        c = self.cfg.profit_optimizer.exploration_coefficient
        total_pulls = sum(s.pulls for s in self.stats.values())
        best_arm, best_ucb = None, float("-inf")
        for a in self.arms:
            s = self.stats[a.arm_id]
            ucb = s.avg_reward + c * math.sqrt(max(1.0, math.log(total_pulls)) / s.pulls)
            if ucb > best_ucb:
                best_ucb, best_arm = ucb, a
        return best_arm

    async def _apply_arm(self, bot: "BybitMarketMaker", arm: OptimizerArm, reason: str):
        # Update live strategy fields safely
        s = bot.config.strategy
        ds = bot.config.strategy.dynamic_spread
        inv = bot.config.strategy.inventory

        # Apply
        object.__setattr__(s, "base_spread_pct", arm.base_spread_pct)
        object.__setattr__(s, "base_order_size_pct_of_balance", arm.order_size_pct_of_balance)
        object.__setattr__(inv, "skew_intensity", arm.skew_intensity)
        object.__setattr__(ds, "volatility_multiplier", arm.vol_multiplier)

        self.logger.info(
            f"[OPT] Switch to {arm.arm_id} | base_spread={arm.base_spread_pct:.6f} "
            f"order_size%={arm.order_size_pct_of_balance:.4f} skew={arm.skew_intensity:.3f} "
            f"vol_mult={arm.vol_multiplier:.2f} | reason={reason}"
        )

        await self.db.log_optimizer_event("switch", arm.arm_id, {
            "base_spread_pct": str(arm.base_spread_pct),
            "order_size_pct_of_balance": str(arm.order_size_pct_of_balance),
            "skew_intensity": str(arm.skew_intensity),
            "vol_multiplier": str(arm.vol_multiplier)
        }, None, reason)

        # Optional: cancel existing orders so the new params take effect immediately
        if self.cfg.profit_optimizer.force_cancel_on_switch:
            await bot._cancel_all_orders()

        self.current_arm_id = arm.arm_id
        self.last_switch_time = time.time()
        self.baseline_snapshot = self._metrics_snapshot(bot)

    async def tick(self, bot: "BybitMarketMaker", now: float):
        if not self.cfg.profit_optimizer.enabled:
            return

        # Delay initial optimization
        if self.last_eval_time == 0.0:
            self.last_eval_time = now
        if (now - self.last_switch_time) == 0.0:
            self.last_switch_time = now

        runtime_since_start = now - bot.state.last_status_report_time if bot.state.last_status_report_time else (now - self.last_eval_time)
        if runtime_since_start < self.cfg.profit_optimizer.min_runtime_before_opt_sec and self.current_arm_id:
            return

        # Initialize first arm if needed
        if self.current_arm_id is None:
            first_arm = self._choose_next_arm_ucb1()
            await self._apply_arm(bot, first_arm, reason="init")
            return

        # Evaluate periodically
        if (now - self.last_eval_time) < self.cfg.profit_optimizer.evaluation_interval_sec:
            return

        window_sec = now - self.last_eval_time
        self.last_eval_time = now

        # Need a minimum number of trades to evaluate
        total_trades = bot.state.metrics.total_trades
        if not hasattr(self, "_last_trade_count"):
            self._last_trade_count = total_trades

        trades_in_window = total_trades - self._last_trade_count
        self._last_trade_count = total_trades

        if trades_in_window < self.cfg.profit_optimizer.min_trades_per_window:
            await self.db.log_optimizer_event("skip", self.current_arm_id, {}, None, f"insufficient_trades({trades_in_window})")
            return

        # Compute reward for current arm
        before = self.baseline_snapshot or self._metrics_snapshot(bot)
        after = self._metrics_snapshot(bot)
        reward_per_hour = self._compute_reward_per_hour(before, after, window_sec, bot)

        cur_stats = self.stats[self.current_arm_id]
        cur_stats.pulls += 1
        cur_stats.total_reward += reward_per_hour
        await self.db.log_optimizer_stats(self.current_arm_id, cur_stats.pulls, cur_stats.avg_reward, cur_stats.total_reward)
        await self.db.log_optimizer_event("score", self.current_arm_id, {}, reward_per_hour, f"trades={trades_in_window}")

        # Cooldown check
        if (now - self.last_switch_time) < self.cfg.profit_optimizer.switch_cooldown_sec:
            return

        # Choose next arm
        next_arm = self._choose_next_arm_ucb1()
        if next_arm.arm_id != self.current_arm_id:
            await self._apply_arm(bot, next_arm, reason="ucb_switch")
        else:
            # refresh baseline for next window
            self.baseline_snapshot = after
```

6) Wire it into the bot
- Create and store the optimizer in BybitMarketMaker.__init__
```python
class BybitMarketMaker:
    def __init__(self, config: Config):
        # ... existing ...
        self.profit_optimizer = ProfitOptimizer(self.config, self.logger, self.db_manager)
        # ...
```

- Tick the optimizer every loop
In _main_loop_tick, near the end (after order management and status logging is fine), add:
```python
        # Run profit optimizer tick
        await self.profit_optimizer.tick(self, current_time)
```

7) Persist optimizer state
- Load on startup: in _load_bot_state, add after you process other items:
```python
        opt_state = state_data.get('optimizer')
        if opt_state:
            self.profit_optimizer.load_state(opt_state)
```
- Save on shutdown: in stop(), add optimizer state into state_to_save:
```python
        state_to_save['optimizer'] = self.profit_optimizer.export_state()
```

That’s it. The optimizer will:
- Start with an initial safe arm.
- Every evaluation window (default 5 minutes), if at least 2 trades happened, compute reward per hour, update stats, and, if out of cooldown, switch to the arm with the best UCB value.
- Persist decisions/stats and survive restarts.

Tips and knobs
- Want slower/faster adaptation? Raise/lower evaluation_interval_sec and switch_cooldown_sec.
- Want more exploration? Increase exploration_coefficient.
- Larger/smaller steps? Edit the grid_* tuples or ranges (kept conservative by default).
- If you’d rather not cancel orders on switch, set force_cancel_on_switch=False (then orders will drift to new prices as they refresh).

If you want this to optimize additional knobs (e.g., min_profit_spread_after_fees_pct or circuit breaker thresholds), say the word and I’ll extend the arms and safety rails.
```python
import asyncio
import logging
import optuna
from decimal import Decimal
import sys
import os
from dataclasses import replace
import json
import argparse  # Added for command-line arguments
from typing import Dict, Any
from tqdm import tqdm  # Added for progress bars; install with pip install tqdm

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
optimizer_logger.setLevel(logging.INFO)  # Ensure optimizer logger is INFO level

def create_trial_config(base_config: Config, trial_params: Dict[str, Any]) -> Config:
    """
    Creates a new Config object by replacing strategy-related parameters
    from the base_config with values suggested by an Optuna trial.
    Handles nested frozen dataclasses and validates the new config.
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
        base_config.strategy.inventory,  # Start with base inventory config
        enabled=inventory_enabled,
        skew_intensity=Decimal(str(skew_intensity)),
        max_inventory_ratio=Decimal(str(max_inventory_ratio))
    )

    # Create new nested dataclass instances for DynamicSpreadConfig
    new_dynamic_spread_config = replace(
        base_config.strategy.dynamic_spread,  # Start with base dynamic spread config
        enabled=dynamic_spread_enabled,
        volatility_multiplier=Decimal(str(volatility_multiplier)),
        price_change_smoothing_factor=Decimal(str(price_change_smoothing_factor))
    )

    # Create a new StrategyConfig instance with all updated nested configs and direct parameters
    new_strategy_config = replace(
        base_config.strategy,  # Start with base strategy config
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
    
    # Validate the new config to catch any invalid combinations early
    try:
        new_config.__post_init__()  # Run post-init validation
    except ConfigurationError as e:
        raise ConfigurationError(f"Invalid trial config: {e}")
    
    # Ensure no unused params
    if trial_params:
        raise ValueError(f"Unused trial parameters: {trial_params}")
    
    return new_config

async def run_simulation_for_trial(trial_config: Config, duration_ticks: int = 2000) -> Decimal:
    """
    Runs a simulation of the market maker bot with the given configuration
    and returns the net realized PnL.
    
    Args:
        trial_config: The Config object for the current trial.
        duration_ticks: Number of main loop iterations to run the simulation.
                        Each tick simulates `trial_config.system.loop_interval_sec` period.
    Returns:
        The net realized PnL as Decimal. Returns Decimal('-inf') if an error occurs.
    """
    bot = None
    try:
        # Initialize the bot with the trial-specific configuration
        bot = BybitMarketMaker(trial_config)
        
        # Initialize bot without connecting real websockets (as it's SIMULATION mode)
        await bot._initialize_bot()

        # Run the main loop for a fixed number of ticks with progress bar
        for _ in tqdm(range(duration_ticks), desc="Simulation Progress", leave=False):
            # In SIMULATION mode, _main_loop_tick internally handles price updates
            # via a simple random walk and simulates order fills.
            await bot._main_loop_tick()
            
            # Simulate the passage of time. This is crucial for features like
            # order stale checks, circuit breakers, and price history tracking.
            await asyncio.sleep(trial_config.system.loop_interval_sec)

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
            await bot.stop()  # This method calls _shutdown_bot, which closes DB, clears state etc.

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
        "base_spread_pct", 0.0001, 0.005, log=True
    )  # Range: 0.01% to 0.5%
    base_order_size_pct_of_balance = trial.suggest_float(
        "base_order_size_pct_of_balance", 0.001, 0.02, step=0.001
    )  # Range: 0.1% to 2.0%, step 0.1%
    max_outstanding_orders = trial.suggest_int(
        "max_outstanding_orders", 1, 10
    )  # Range: 1 to 10 orders
    min_profit_spread_after_fees_pct = trial.suggest_float(
        "min_profit_spread_after_fees_pct", 0.00001, 0.0005, log=True
    )  # Range: 0.001% to 0.05%

    # Dynamic spread parameters
    dynamic_spread_enabled = trial.suggest_categorical(
        "dynamic_spread_enabled", [True, False]
    )
    # Volatility multiplier and smoothing factor are only relevant if dynamic spread is enabled
    volatility_multiplier = trial.suggest_float(
        "volatility_multiplier", 0.1, 5.0
    ) if dynamic_spread_enabled else 0.0  # Set to 0 if disabled
    price_change_smoothing_factor = trial.suggest_float(
        "price_change_smoothing_factor", 0.1, 0.9, step=0.1
    ) if dynamic_spread_enabled else 0.0  # Set to 0 if disabled

    # Inventory strategy parameters
    inventory_enabled = trial.suggest_categorical(
        "inventory_enabled", [True, False]
    )
    # Skew intensity and max inventory ratio are only relevant if inventory strategy is enabled
    skew_intensity = trial.suggest_float(
        "skew_intensity", 0.1, 2.0
    ) if inventory_enabled else 0.0  # Set to 0 if disabled
    max_inventory_ratio = trial.suggest_float(
        "max_inventory_ratio", 0.05, 0.95, step=0.05
    ) if inventory_enabled else 0.0  # Set to 0 if disabled

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
        api_key="SIM_KEY",  # Dummy API key for simulation mode
        api_secret="SIM_SECRET",  # Dummy API secret for simulation mode
        testnet=False,  # Simulation mode does not interact with Bybit, so testnet setting is irrelevant
        trading_mode="SIMULATION",  # Ensure we are always in simulation mode for optimization
        symbol="XLMUSDT",  # Example symbol; keep consistent for meaningful optimization
        category="linear",  # Example category; keep consistent
        leverage=Decimal('1'),  # For simplicity in simulation, use 1x leverage
        min_order_value_usd=Decimal('10'),  # Minimum order value
        max_order_size_pct=Decimal('0.1'),  # Max individual order size as % of balance
        max_net_exposure_usd=Decimal('1000'),  # Max total exposure in USD
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
        initial_dry_run_capital=Decimal('10000')  # Starting capital for the simulation
    )

    # Create the trial-specific configuration by merging base_config with trial_params
    trial_config = create_trial_config(base_config, trial_params)

    # Run the simulation with the generated trial configuration
    net_pnl = asyncio.run(run_simulation_for_trial(trial_config))
    
    # Optuna aims to maximize the objective function, so we return the net realized PnL
    # If PNL is -inf, Optuna will handle it as a poor performer
    return float(net_pnl)

if __name__ == "__main__":
    # --- Command-Line Argument Parsing ---
    parser = argparse.ArgumentParser(description="Profit Optimizer for Bybit Market Maker Bot")
    parser.add_argument("--num-trials", type=int, default=100, help="Number of trials to run")
    parser.add_argument("--timeout", type=int, default=7200, help="Optimization timeout in seconds")
    parser.add_argument("--n-jobs", type=int, default=1, help="Number of parallel jobs (use with caution for async code)")
    parser.add_argument("--study-name", type=str, default="market_maker_profit_opt_v3", help="Optuna study name")
    args = parser.parse_args()

    # --- Pre-check: Ensure the market maker bot's code file exists ---
    market_maker_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "marketmaker1_0.py")
    if not os.path.exists(market_maker_file):
        optimizer_logger.error(f"Error: Required file '{market_maker_file}' not found.")
        optimizer_logger.error("Please ensure the market maker bot's code is saved as 'marketmaker1_0.py' in the same directory.")
        sys.exit(1)

    # --- Optuna Study Setup ---
    # Define a unique name for the study and its storage database
    study_name = args.study_name
    storage_path = f"sqlite:///{study_name}.db"

    optimizer_logger.info(f"Creating/Loading Optuna study: '{study_name}' from '{storage_path}'")
    # Create or load an existing Optuna study.
    # `load_if_exists=True` allows resuming optimization from a previous run.
    # Use TPESampler for better sampling and MedianPruner to stop bad trials early.
    study = optuna.create_study(
        direction="maximize",  # We aim to maximize the Net Realized PnL
        study_name=study_name,
        storage=storage_path,
        load_if_exists=True,
        sampler=optuna.samplers.TPESampler(),  # Tree-structured Parzen Estimator for better optimization
        pruner=optuna.pruners.MedianPruner(n_warmup_steps=10)  # Prune poor trials after 10 steps
    )

    # --- Optimization Parameters ---
    num_trials = args.num_trials  # Number of new trials to run in this optimization session
    timeout_seconds = args.timeout  # Maximum optimization time in seconds
    n_jobs = args.n_jobs  # Parallel jobs (warning: async code may need careful handling)
    
    optimizer_logger.info(f"Starting optimization for {num_trials} new trials or {timeout_seconds} seconds with {n_jobs} parallel jobs.")
    optimizer_logger.info("This process will run multiple bot simulations and might take significant time.")
    optimizer_logger.info("Intermediate results and study state are saved to the SQLite database.")

    # --- Run Optimization ---
    try:
        study.optimize(objective, n_trials=num_trials, timeout=timeout_seconds, n_jobs=n_jobs)
    except KeyboardInterrupt:
        optimizer_logger.info("Optimization interrupted by user (KeyboardInterrupt).")
    except Exception as e:
        optimizer_logger.error(f"An unexpected error occurred during optimization: {e}", exc_info=True)

    optimizer_logger.info("\nOptimization finished.")

    # --- Report Best Results ---
    if study.trials:
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
    else:
        optimizer_logger.warning("No trials were run during this session.")

    # --- Save all trial results to CSV ---
    try:
        import pandas as pd
        df = study.trials_dataframe()
        csv_file = f"{study_name}_results.csv"
        df.to_csv(csv_file, index=False)
        optimizer_logger.info(f"All optimization results saved to '{csv_file}'.")
    except ImportError:
        optimizer_logger.warning("Pandas not installed. Cannot save trials to CSV. Install with 'pip install pandas'.")
    except Exception as e:
        optimizer_logger.error(f"Failed to save trials dataframe to CSV: {e}", exc_info=True)
```