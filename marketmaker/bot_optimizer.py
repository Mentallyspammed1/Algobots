import argparse
import logging
from copy import deepcopy
from datetime import datetime, timezone

import optuna

from backtest import BacktestParams, MarketMakerBacktester
from config import Config

logger = logging.getLogger("BotOptimizer")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


def objective(trial: optuna.Trial) -> float:
    # Load base configuration
    base_config = Config()

    # Suggest parameters for optimization
    # Spread
    base_spread = trial.suggest_float("BASE_SPREAD", 0.0005, 0.005, log=True)
    min_spread = trial.suggest_float("MIN_SPREAD", 0.0001, base_spread, log=True)
    max_spread = trial.suggest_float("MAX_SPREAD", base_spread, 0.02, log=True)

    # Order Management
    order_levels = trial.suggest_int("ORDER_LEVELS", 1, 10)
    min_order_size = trial.suggest_float("MIN_ORDER_SIZE", 0.0001, 0.01, log=True)
    order_size_increment = trial.suggest_float("ORDER_SIZE_INCREMENT", 0.0, 0.005)

    # Risk Management
    max_position = trial.suggest_float("MAX_POSITION", 0.01, 1.0, log=True)
    inventory_extreme = trial.suggest_float("INVENTORY_EXTREME", 0.5, 0.95)
    stop_loss_pct = trial.suggest_float("STOP_LOSS_PCT", 0.001, 0.05, log=True)
    take_profit_pct = trial.suggest_float("TAKE_PROFIT_PCT", 0.001, 0.05, log=True)

    # Volatility
    volatility_window = trial.suggest_int("VOLATILITY_WINDOW", 10, 100)
    volatility_std = trial.suggest_float("VOLATILITY_STD", 1.0, 3.0)

    # Backtest specific parameters (from BacktestParams)
    maker_fee = trial.suggest_float("maker_fee", -0.00025, 0.0005)
    volume_cap_ratio = trial.suggest_float("volume_cap_ratio", 0.05, 0.5)

    # Apply suggested parameters to a copy of the config
    cfg = deepcopy(base_config)
    cfg.BASE_SPREAD = base_spread
    cfg.MIN_SPREAD = min_spread
    cfg.MAX_SPREAD = max_spread
    cfg.ORDER_LEVELS = order_levels
    cfg.MIN_ORDER_SIZE = min_order_size
    cfg.ORDER_SIZE_INCREMENT = order_size_increment
    cfg.MAX_POSITION = max_position
    cfg.INVENTORY_EXTREME = inventory_extreme
    cfg.STOP_LOSS_PCT = stop_loss_pct
    cfg.TAKE_PROFIT_PCT = take_profit_pct
    cfg.VOLATILITY_WINDOW = volatility_window
    cfg.VOLATILITY_STD = volatility_std

    # Set up BacktestParams (using values from config and trial)
    params = BacktestParams(
        symbol=cfg.SYMBOL,
        category=cfg.CATEGORY,
        interval=cfg.INTERVAL,
        start=datetime.strptime(cfg.START_DATE, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        ),
        end=datetime.strptime(cfg.END_DATE, "%Y-%m-%d").replace(tzinfo=timezone.utc),
        testnet=cfg.TESTNET,
        maker_fee=maker_fee,
        volume_cap_ratio=volume_cap_ratio,
    )

    # Instantiate and run the backtester
    backtester = MarketMakerBacktester(params, cfg=cfg)
    results = backtester.run()

    # Return the metric to optimize (e.g., net_pnl)
    net_pnl = results.get("net_pnl", 0.0)
    sharpe_like = results.get("sharpe_like", 0.0)

    # Optuna can maximize or minimize. We want to maximize profit.
    # You can choose to optimize net_pnl or sharpe_like
    # For now, let's maximize net_pnl
    trial.set_user_attr("net_pnl", net_pnl)
    trial.set_user_attr("sharpe_like", sharpe_like)
    trial.set_user_attr("max_drawdown", results.get("max_drawdown", 0.0))

    return net_pnl


def main():
    parser = argparse.ArgumentParser(
        description="Optimize Market Maker Bot parameters using Optuna."
    )
    parser.add_argument(
        "--trials", type=int, default=50, help="Number of optimization trials."
    )
    parser.add_argument(
        "--study-name",
        type=str,
        default="market_maker_optimization",
        help="Name of the Optuna study.",
    )
    parser.add_argument(
        "--storage",
        type=str,
        default=None,
        help="Optuna storage URL (e.g., sqlite:///db.sqlite3).",
    )
    parser.add_argument(
        "--direction",
        type=str,
        default="maximize",
        choices=["maximize", "minimize"],
        help="Optimization direction.",
    )

    args = parser.parse_args()

    # Create or load Optuna study
    study = optuna.create_study(
        study_name=args.study_name,
        direction=args.direction,
        storage=args.storage,
        load_if_exists=True,
    )

    logger.info(f"Starting optimization with {args.trials} trials...")
    study.optimize(objective, n_trials=args.trials)

    logger.info("Optimization finished.")
    logger.info(f"Best trial: {study.best_trial.value:.4f}")
    logger.info("Best parameters:")
    for key, value in study.best_trial.params.items():
        logger.info(f"  {key}: {value}")

    # Save results to CSV
    df_results = study.trials_dataframe()
    df_results.to_csv(f"{args.study_name}_results.csv", index=False)
    logger.info(f"Optimization results saved to {args.study_name}_results.csv")


if __name__ == "__main__":
    main()
