# profit_optimizer.py
import argparse
import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, Any

import numpy as np
import optuna
import pandas as pd

from config import Config
from backtest import BacktestParams, MarketMakerBacktester, BybitHistoricalData, from_ms

logger = logging.getLogger("ProfitOptimizer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def fetch_klines_once(params: BacktestParams) -> pd.DataFrame:
    logger.info("Fetching klines once for the entire optimization window...")
    df = BybitHistoricalData(params).get_klines()
    logger.info(f"Fetched {len(df)} candles from {from_ms(int(df.start.iloc[0]))} "
                f"to {from_ms(int(df.start.iloc[-1]))}")
    return df


def patch_bt_to_use_df(bt: MarketMakerBacktester, df_klines: pd.DataFrame):
    """
    Monkey-patch the backtester to reuse the pre-fetched klines.
    """
    bt.data.get_klines = lambda: df_klines


def apply_trial_to_config(base_cfg: Config, tr: optuna.Trial) -> Config:
    """
    Map Optuna suggestions to your Config fields.
    Adjust ranges to suit your market and instrument.
    """
    cfg = deepcopy(base_cfg)

    # Spreads
    min_spread = tr.suggest_float("MIN_SPREAD", 5e-5, 1e-3, log=True)
    base_spread_raw = tr.suggest_float("BASE_SPREAD_raw", 1e-4, 5e-3, log=True)
    base_spread = max(base_spread_raw, min_spread)
    max_spread = tr.suggest_float("MAX_SPREAD", base_spread * 1.5, 2e-2, log=True)

    # Order ladder
    order_levels = tr.suggest_int("ORDER_LEVELS", 1, 8)
    min_order_size = tr.suggest_float("MIN_ORDER_SIZE", 0.001, 0.2, log=True)
    order_size_increment = tr.suggest_float("ORDER_SIZE_INCREMENT", 0.0, min_order_size, log=False)

    # Inventory control
    max_position = tr.suggest_float("MAX_POSITION", min_order_size * order_levels, min_order_size * order_levels * 20, log=True)
    inventory_extreme = tr.suggest_float("INVENTORY_EXTREME", 0.6, 1.0)

    # Volatility model
    vol_window = tr.suggest_int("VOLATILITY_WINDOW", 20, 200)
    vol_std = tr.suggest_float("VOLATILITY_STD", 1.0, 3.0)

    # Risk management
    stop_loss_pct = tr.suggest_float("STOP_LOSS_PCT", 0.002, 0.02, log=True)
    take_profit_pct = tr.suggest_float("TAKE_PROFIT_PCT", 0.002, 0.03, log=True)

    # Write back to cfg
    cfg.MIN_SPREAD = float(min_spread)
    cfg.BASE_SPREAD = float(base_spread)
    cfg.MAX_SPREAD = float(max_spread)
    cfg.ORDER_LEVELS = int(order_levels)
    cfg.MIN_ORDER_SIZE = float(min_order_size)
    cfg.ORDER_SIZE_INCREMENT = float(order_size_increment)
    cfg.MAX_POSITION = float(max_position)
    cfg.INVENTORY_EXTREME = float(inventory_extreme)
    cfg.VOLATILITY_WINDOW = int(vol_window)
    cfg.VOLATILITY_STD = float(vol_std)
    cfg.STOP_LOSS_PCT = float(stop_loss_pct)
    cfg.TAKE_PROFIT_PCT = float(take_profit_pct)

    return cfg


def make_objective(
    base_params: BacktestParams,
    df_klines: pd.DataFrame,
    base_cfg: Config,
    metric: str,
    risk_penalty: float,
    max_dd_cap: float,
    trials_verbose: bool
):
    """
    Returns an Optuna objective callable.
    metric: 'net' (net pnl - risk_penalty * drawdown) or 'sharpe'
    """
    assert metric in ("net", "sharpe")

    def objective(trial: optuna.Trial) -> float:
        # Backtest params per-trial (can also be tuned)
        params = deepcopy(base_params)
        params.maker_fee = trial.suggest_float("maker_fee", -0.00025, 0.0006)  # allow rebates or fees
        params.volume_cap_ratio = trial.suggest_float("volume_cap_ratio", 0.05, 0.6)
        params.fill_on_touch = trial.suggest_categorical("fill_on_touch", [True, False])
        params.rng_seed = trial.suggest_int("rng_seed", 1, 10)

        # Config per-trial
        cfg = apply_trial_to_config(base_cfg, trial)

        # Run backtest
        bt = MarketMakerBacktester(params, cfg=cfg)
        patch_bt_to_use_df(bt, df_klines)
        results = bt.run()

        net = float(results["net_pnl"])
        dd = float(results["max_drawdown"])
        sharpe_like = float(results["sharpe_like"])

        # Hard cap on max drawdown if provided
        if max_dd_cap is not None and dd > max_dd_cap:
            # Infeasible solution — penalize heavily
            score = -1e9
        else:
            if metric == "net":
                score = net - risk_penalty * dd
            else:
                score = sharpe_like

        if trials_verbose:
            logger.info(f"Trial {trial.number}: net={net:.4f}, dd={dd:.4f}, sharpe={sharpe_like:.3f}, score={score:.5f}")

        # Attach extras for inspection
        trial.set_user_attr("net_pnl", net)
        trial.set_user_attr("max_drawdown", dd)
        trial.set_user_attr("sharpe_like", sharpe_like)
        return float(score)

    return objective


def main():
    ap = argparse.ArgumentParser(description="Profit optimizer for MarketMaker using Optuna + Bybit historical data")
    ap.add_argument("--symbol", type=str, default="BTCUSDT")
    ap.add_argument("--category", type=str, default="linear", choices=["linear", "inverse", "spot"])
    ap.add_argument("--interval", type=str, default="1", help="Bybit kline interval: 1,3,5,15,60,240,D,...")
    ap.add_argument("--start", type=str, required=True, help="UTC start, e.g. 2024-06-01T00:00:00")
    ap.add_argument("--end", type=str, required=True, help="UTC end, e.g. 2024-06-07T00:00:00")
    ap.add_argument("--testnet", action="store_true")

    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--n-jobs", type=int, default=1, help="Parallel workers for Optuna")
    ap.add_argument("--metric", type=str, default="net", choices=["net", "sharpe"], help="Optimization target")
    ap.add_argument("--risk-penalty", type=float, default=0.25, help="Penalty lambda for drawdown when metric=net")
    ap.add_argument("--max-dd-cap", type=float, default=None, help="Hard cap on max drawdown; infeasible if exceeded")
    ap.add_argument("--storage", type=str, default=None, help="Optuna storage, e.g., sqlite:///profit_opt.db (enables parallel)")
    ap.add_argument("--study-name", type=str, default="mm_profit_opt")
    ap.add_argument("--sampler", type=str, default="tpe", choices=["tpe", "cmaes", "random"])
    ap.add_argument("--pruner", type=str, default="median", choices=["none", "median", "hnp"])
    ap.add_argument("--trials-verbose", action="store_true")
    ap.add_argument("--save-results", type=str, default="opt_results.csv")

    args = ap.parse_args()

    base_params = BacktestParams(
        symbol=args.symbol,
        category=args.category,
        interval=args.interval,
        start=parse_dt(args.start),
        end=parse_dt(args.end),
        testnet=args.testnet,
        # maker_fee, volume_cap_ratio, rng_seed, fill_on_touch will be tuned per trial
    )

    # Fetch data once
    df_klines = fetch_klines_once(base_params)

    # Base config to be tuned
    base_cfg = Config()
    base_cfg.SYMBOL = args.symbol
    base_cfg.CATEGORY = args.category

    # Sampler / Pruner
    if args.sampler == "tpe":
        sampler = optuna.samplers.TPESampler(seed=42, multivariate=True)
    elif args.sampler == "cmaes":
        sampler = optuna.samplers.CmaEsSampler(seed=42)
    else:
        sampler = optuna.samplers.RandomSampler(seed=42)

    if args.pruner == "median":
        pruner = optuna.pruners.MedianPruner(n_startup_trials=10, n_warmup_steps=0)
    elif args.pruner == "hnp":
        pruner = optuna.pruners.HyperbandPruner()
    else:
        pruner = optuna.pruners.NopPruner()

    # Study
    storage = args.storage if args.storage else None
    study = optuna.create_study(
        study_name=args.study_name,
        direction="maximize",
        sampler=sampler,
        pruner=pruner,
        storage=storage,
        load_if_exists=bool(storage),
    )

    # Optimize
    obj = make_objective(
        base_params=base_params,
        df_klines=df_klines,
        base_cfg=base_cfg,
        metric=args.metric,
        risk_penalty=args.risk_penalty,
        max_dd_cap=args.max_dd_cap,
        trials_verbose=args.trials_verbose
    )

    logger.info(f"Starting optimization for {args.trials} trials (parallel n_jobs={args.n_jobs}) ...")
    study.optimize(obj, n_trials=args.trials, n_jobs=args.n_jobs, show_progress_bar=True)

    # Results
    best = study.best_trial
    logger.info("Optimization complete.")
    logger.info(f"Best score: {best.value:.6f}")
    logger.info(f"Best params:n{json.dumps(best.params, indent=2)}")
    logger.info(f"Best metrics: net={best.user_attrs.get('net_pnl'):.6f}, "
                f"dd={best.user_attrs.get('max_drawdown'):.6f}, "
                f"sharpe={best.user_attrs.get('sharpe_like'):.4f}")

    # Save all trials to CSV
    records = []
    for t in study.trials:
        row = {
            "number": t.number,
            "value": t.value,
            "state": str(t.state),
            "net_pnl": t.user_attrs.get("net_pnl"),
            "max_drawdown": t.user_attrs.get("max_drawdown"),
            "sharpe_like": t.user_attrs.get("sharpe_like"),
        }
        row.update(t.params)
        records.append(row)
    df_results = pd.DataFrame.from_records(records)
    df_results.to_csv(args.save_results, index=False)
    logger.info(f"Saved results to {args.save_results}")

    # Optional: re-run the backtest with best settings and dump equity curve
    logger.info("Re-running backtest with best parameters to export equity curve...")
    cfg_best = apply_trial_to_config(base_cfg, best)
    params_best = deepcopy(base_params)
    params_best.maker_fee = best.params["maker_fee"]
    params_best.volume_cap_ratio = best.params["volume_cap_ratio"]
    params_best.fill_on_touch = best.params["fill_on_touch"]
    params_best.rng_seed = best.params["rng_seed"]

    bt = MarketMakerBacktester(params_best, cfg=cfg_best)
    patch_bt_to_use_df(bt, df_klines)
    bt.run()
    eq = pd.DataFrame(bt.equity_curve, columns=["timestamp_ms", "equity"])
    eq["timestamp"] = eq["timestamp_ms"].apply(lambda x: from_ms(x).isoformat())
    eq.to_csv("equity_curve_best.csv", index=False)
    logger.info("Saved equity_curve_best.csv")

if __name__ == "__main__":
    main()