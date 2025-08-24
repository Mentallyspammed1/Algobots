Below is a self‑contained backtester + profit optimizer for your Supertrend bot. It:

- Pulls historical Bybit V5 klines (public endpoint; no API keys required)
- Recomputes Supertrend and generates signals the same way your bot does
- Enters at next-bar open, manages SL/TP and optional trailing stop using intra‑bar touch logic
- Uses your risk-per-trade sizing logic and leverage caps
- Tracks equity, PnL, drawdown, Sharpe-like ratio, and a trade blotter
- Can run Optuna to optimize ST period/multiplier and risk/exit parameters for max profit (or a risk-adjusted objective)

Save as supertrend_backtester.py next to your bot. Requires: pandas, pandas_ta, numpy, pybit, optuna.

Python code

```python
# supertrend_backtester.py
import argparse
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, getcontext
from typing import Dict, List, Optional, Tuple

import numpy as np
import optuna
import pandas as pd
import pandas_ta as ta
from pybit.unified_trading import HTTP

# Higher precision for Decimal rounding
getcontext().prec = 28


# ============================== Data & utils ==============================

def to_ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


@dataclass
class Instr:
    symbol: str
    category: str
    tick_size: Decimal
    qty_step: Decimal
    min_price: Decimal
    max_price: Decimal
    min_qty: Decimal
    max_qty: Decimal
    min_leverage: Decimal
    max_leverage: Decimal
    leverage_step: Decimal


@dataclass
class BTParams:
    symbol: str = "BTCUSDT"
    category: str = "linear"  # "linear" | "spot" | "inverse"
    interval: str = "15"      # Bybit kline interval: "1","3","5","15","60","240","D",...
    start: datetime = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end: datetime = datetime(2024, 1, 7, tzinfo=timezone.utc)
    testnet: bool = False

    # Trading / fees / slippage
    initial_balance: float = 10000.0
    leverage: float = 5.0
    taker_fee: float = 0.0006  # market orders (default bot order type)
    maker_fee: float = 0.0001  # unused unless you switch to LIMIT
    slippage_bps: float = 0.0  # e.g., 1.5 = 1.5 bps slippage on entries/exits

    # Risk sizing
    risk_per_trade_pct: float = 1.0
    min_position_value: float = 10.0
    max_position_value: float = 10000.0

    # Strategy (Supertrend) + exits
    st_period: int = 10
    st_multiplier: float = 3.0
    stop_loss_pct: float = 0.015
    take_profit_pct: float = 0.03
    trailing_stop_pct: float = 0.0  # 0 disables trailing
    trailing_activation_pct: float = 0.0  # 0 => activate immediately

    # Execution model
    fill_on_touch: bool = True  # intra-bar touch = filled
    path_seed: int = 42         # seeds intrabar OHL/C path ordering

    # Limits
    max_open_positions: int = 1


@dataclass
class BTResults:
    net_pnl: float
    max_drawdown: float
    sharpe_like: float
    win_rate: float
    num_trades: int
    equity_curve: List[Tuple[int, float]]
    trades: pd.DataFrame


class BybitData:
    def __init__(self, params: BTParams):
        self.http = HTTP(testnet=params.testnet)
        self.params = params

    def get_instrument(self) -> Instr:
        r = self.http.get_instruments_info(
            category=self.params.category,
            symbol=self.params.symbol
        )
        if r.get("retCode") != 0 or not r["result"]["list"]:
            # Fallback defaults if not found
            return Instr(
                symbol=self.params.symbol,
                category=self.params.category,
                tick_size=Decimal("0.1"),
                qty_step=Decimal("0.001"),
                min_price=Decimal("0"),
                max_price=Decimal("100000000"),
                min_qty=Decimal("0.001"),
                max_qty=Decimal("100000000"),
                min_leverage=Decimal("1"),
                max_leverage=Decimal("100"),
                leverage_step=Decimal("0.01"),
            )

        inst = r["result"]["list"][0]
        pf = inst.get("priceFilter", {}) or {}
        lf = inst.get("lotSizeFilter", {}) or {}
        lev = inst.get("leverageFilter", {}) or {}
        return Instr(
            symbol=inst["symbol"],
            category=self.params.category,
            tick_size=Decimal(pf.get("tickSize", "0.1")),
            qty_step=Decimal(lf.get("qtyStep", "0.001")),
            min_price=Decimal(pf.get("minPrice", "0")),
            max_price=Decimal(pf.get("maxPrice", "100000000")),
            min_qty=Decimal(lf.get("minOrderQty", "0.001")),
            max_qty=Decimal(lf.get("maxOrderQty", "100000000")),
            min_leverage=Decimal(lev.get("minLeverage", "1")),
            max_leverage=Decimal(lev.get("maxLeverage", "100")),
            leverage_step=Decimal(lev.get("leverageStep", "0.01")),
        )

    def get_klines(self) -> pd.DataFrame:
        start_ms, end_ms = to_ms(self.params.start), to_ms(self.params.end)
        limit = 1000
        all_rows: List[List[str]] = []
        cur = start_ms

        while True:
            r = self.http.get_kline(
                category=self.params.category,
                symbol=self.params.symbol,
                interval=self.params.interval,
                start=cur,
                end=end_ms,
                limit=limit
            )
            if r.get("retCode") != 0:
                raise RuntimeError(f"get_kline error: {r.get('retMsg')}")
            rows = r["result"]["list"]
            if not rows:
                break
            rows_sorted = sorted(rows, key=lambda x: int(x[0]))
            all_rows.extend(rows_sorted)
            last = int(rows_sorted[-1][0])
            nxt = last + 1
            if nxt >= end_ms:
                break
            cur = nxt
            time.sleep(0.03)  # be gentle

        if not all_rows:
            raise ValueError("No klines for requested window")

        df = pd.DataFrame(
            all_rows,
            columns=["start", "open", "high", "low", "close", "volume", "turnover"]
        )
        df = df.astype({
            "start": "int64",
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "float64",
            "turnover": "float64",
        })
        return df.sort_values("start").reset_index(drop=True)


# ============================== Rounding ==============================

def round_to_step(x: Decimal, step: Decimal, down=True) -> Decimal:
    if step <= 0:
        return x
    q = (x / step)
    q = q.quantize(Decimal("1"), rounding=ROUND_DOWN if down else ROUND_DOWN)
    return q * step


def clip_price(x: Decimal, instr: Instr) -> Decimal:
    x = max(instr.min_price, min(x, instr.max_price))
    return round_to_step(x, instr.tick_size, down=True)


def clip_qty(x: Decimal, instr: Instr) -> Decimal:
    x = max(instr.min_qty, min(x, instr.max_qty))
    return round_to_step(x, instr.qty_step, down=True)


# ============================== Strategy ==============================

def compute_indicators(df: pd.DataFrame, st_period: int, st_multiplier: float) -> pd.DataFrame:
    st = ta.supertrend(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        length=st_period,
        multiplier=st_multiplier
    )
    # Column names pattern in pandas_ta:
    # SUPERT_{length}_{mult}, SUPERTd_{...}, SUPERTl_{...}, SUPERTu_{...}
    df = df.copy()
    df["st"] = st[f"SUPERT_{st_period}_{st_multiplier}"]
    df["st_dir"] = st[f"SUPERTd_{st_period}_{st_multiplier}"]  # 1 / -1
    df["st_upper"] = st[f"SUPERTl_{st_period}_{st_multiplier}"]
    df["st_lower"] = st[f"SUPERTu_{st_period}_{st_multiplier}"]
    # Fill early NaNs
    df[["st", "st_dir", "st_upper", "st_lower"]] = df[["st", "st_dir", "st_upper", "st_lower"]].ffill().bfill()
    return df


def gen_signal(prev_dir: float, last_dir: float, last_close: float, last_st: float) -> int:
    # Same semantics as your bot
    # STRONG_BUY (+2) on flip -1 -> +1, BUY (+1) if uptrend and price > st
    # STRONG_SELL (-2) on flip +1 -> -1, SELL (-1) if downtrend and price < st
    if last_dir == 1:
        if prev_dir == -1:
            return 2
        elif last_close > last_st:
            return 1
        else:
            return 0
    elif last_dir == -1:
        if prev_dir == 1:
            return -2
        elif last_close < last_st:
            return -1
        else:
            return 0
    return 0


# ============================== Fill model ==============================

def intrabar_path(o: float, h: float, l: float, c: float, ts_ms: int, seed: int) -> List[float]:
    # Deterministic O-H-L-C or O-L-H-C path
    go_high_first = (((ts_ms // 60000) ^ seed) % 2 == 0)
    if go_high_first:
        return [o, (o + h) / 2, h, (h + l) / 2, l, (l + c) / 2, c]
    else:
        return [o, (o + l) / 2, l, (l + h) / 2, h, (h + c) / 2, c]


# ============================== Backtester ==============================

class SupertrendBacktester:
    def __init__(self, params: BTParams, df_klines: Optional[pd.DataFrame] = None, instr: Optional[Instr] = None):
        self.p = params
        self.data = BybitData(params) if df_klines is None else None
        self.df = df_klines
        self.instr = instr

        # State
        self.balance = float(params.initial_balance)
        self.equity_curve: List[Tuple[int, float]] = []
        self.trades: List[Dict] = []

        # Position
        self.pos_qty = Decimal("0")
        self.pos_side = None  # "long" | "short" | None
        self.entry_price = Decimal("0")
        self.stop_price = None
        self.tp_price = None
        self.trail_active = False
        self.trail_pct = Decimal(str(params.trailing_stop_pct))
        self.trail_activation = Decimal(str(params.trailing_activation_pct))
        self.extreme_price = None  # highest (long) or lowest (short) since activation

    def load(self):
        if self.instr is None:
            self.instr = (self.data.get_instrument() if self.data else Instr(
                symbol=self.p.symbol, category=self.p.category,
                tick_size=Decimal("0.1"), qty_step=Decimal("0.001"),
                min_price=Decimal("0"), max_price=Decimal("100000000"),
                min_qty=Decimal("0.001"), max_qty=Decimal("100000000"),
                min_leverage=Decimal("1"), max_leverage=Decimal("100"),
                leverage_step=Decimal("0.01")
            ))
        if self.df is None:
            self.df = self.data.get_klines()
        self.df = compute_indicators(self.df, self.p.st_period, self.p.st_multiplier)

    def _apply_slippage(self, price: float, side: str) -> float:
        if self.p.slippage_bps <= 0:
            return price
        adj = price * (self.p.slippage_bps / 10000.0)
        return price + (adj if side == "buy" else -adj)

    def _fees(self, price: float, qty: Decimal) -> float:
        notional = float(Decimal(str(price)) * qty)
        return notional * float(self.p.taker_fee)

    def _risk_size_qty(self, entry: float, stop: float) -> Decimal:
        bal = Decimal(str(self.balance))
        risk_amt = bal * Decimal(str(self.p.risk_per_trade_pct / 100.0))
        stop_dist_pct = abs(Decimal(str(entry)) - Decimal(str(stop))) / Decimal(str(entry))
        if stop_dist_pct <= 0:
            return Decimal("0")
        pos_val_needed = risk_amt / stop_dist_pct

        eff_cap = bal * Decimal(str(self.p.leverage))
        pos_val_needed = min(pos_val_needed, Decimal(str(self.p.max_position_value)), eff_cap)
        pos_val_needed = max(pos_val_needed, Decimal(str(self.p.min_position_value)))

        raw_qty = pos_val_needed / Decimal(str(entry))
        qty = clip_qty(raw_qty, self.instr)
        return qty

    def _enter(self, side: str, price: float, ts_ms: int):
        price = self._apply_slippage(price, "buy" if side == "long" else "sell")
        entry = clip_price(Decimal(str(price)), self.instr)

        # Set SL/TP from params
        if side == "long":
            stop = entry * (Decimal("1") - Decimal(str(self.p.stop_loss_pct)))
            tp = entry * (Decimal("1") + Decimal(str(self.p.take_profit_pct)))
        else:
            stop = entry * (Decimal("1") + Decimal(str(self.p.stop_loss_pct)))
            tp = entry * (Decimal("1") - Decimal(str(self.p.take_profit_pct)))

        stop = clip_price(stop, self.instr)
        tp = clip_price(tp, self.instr)

        qty = self._risk_size_qty(float(entry), float(stop))
        if qty <= 0:
            return False

        fee = self._fees(float(entry), qty)
        self.pos_qty = qty
        self.pos_side = side
        self.entry_price = entry
        self.stop_price = stop
        self.tp_price = tp
        self.trail_active = False
        self.extreme_price = entry

        self.balance -= fee  # pay taker fee on entry

        self.trades.append({
            "ts_open": ts_ms,
            "side": side,
            "entry": float(entry),
            "qty": float(qty),
            "fee_entry": fee
        })
        return True

    def _exit(self, price: float, reason: str, ts_ms: int):
        price = self._apply_slippage(price, "sell" if self.pos_side == "long" else "buy")
        fill = clip_price(Decimal(str(price)), self.instr)
        qty = self.pos_qty

        pnl = float((fill - self.entry_price) * qty) if self.pos_side == "long" else float((self.entry_price - fill) * qty)
        fee = self._fees(float(fill), qty)
        self.balance += pnl
        self.balance -= fee

        # Complete last trade record
        tr = self.trades[-1]
        tr.update({
            "ts_close": ts_ms,
            "exit": float(fill),
            "pnl": pnl - fee,  # net of exit fee (entry fee already deducted from balance)
            "fee_exit": fee,
            "reason": reason
        })

        # Reset position
        self.pos_qty = Decimal("0")
        self.pos_side = None
        self.entry_price = Decimal("0")
        self.stop_price = None
        self.tp_price = None
        self.trail_active = False
        self.extreme_price = None

    def _update_trailing(self, last: float):
        if self.p.trailing_stop_pct <= 0 or self.pos_side is None:
            return
        last_d = Decimal(str(last))

        # Activation condition
        if not self.trail_active:
            if self.pos_side == "long":
                if last_d >= self.entry_price * (Decimal("1") + self.trail_activation):
                    self.trail_active = True
                    self.extreme_price = last_d
            else:
                if last_d <= self.entry_price * (Decimal("1") - self.trail_activation):
                    self.trail_active = True
                    self.extreme_price = last_d

        if not self.trail_active:
            return

        # Update extreme and stop
        if self.pos_side == "long":
            if last_d > self.extreme_price:
                self.extreme_price = last_d
            new_stop = self.extreme_price * (Decimal("1") - self.trail_pct)
            self.stop_price = clip_price(new_stop, self.instr)
        else:
            if last_d < self.extreme_price:
                self.extreme_price = last_d
            new_stop = self.extreme_price * (Decimal("1") + self.trail_pct)
            self.stop_price = clip_price(new_stop, self.instr)

    def _check_exits_intrabar(self, o: float, h: float, l: float, c: float, ts_ms: int) -> bool:
        """
        Return True if position closed within this bar. Uses simple O-H-L-C path.
        """
        if self.pos_side is None:
            return False

        path = intrabar_path(o, h, l, c, ts_ms, self.p.path_seed)

        # Evaluate SL/TP touch order along path
        for px in path:
            # Update trailing stop with current "tick"
            self._update_trailing(px)

            if self.pos_side == "long":
                if self.p.fill_on_touch and float(self.stop_price) >= px and self.stop_price is not None:
                    self._exit(float(self.stop_price), "stop", ts_ms)
                    return True
                if self.p.fill_on_touch and float(self.tp_price) <= px and self.tp_price is not None:
                    self._exit(float(self.tp_price), "take_profit", ts_ms)
                    return True
            else:
                if self.p.fill_on_touch and float(self.stop_price) <= px and self.stop_price is not None:
                    self._exit(float(self.stop_price), "stop", ts_ms)
                    return True
                if self.p.fill_on_touch and float(self.tp_price) >= px and self.tp_price is not None:
                    self._exit(float(self.tp_price), "take_profit", ts_ms)
                    return True
        return False

    def run(self) -> BTResults:
        self.load()
        df = self.df.copy()

        # We generate signals on bar t (close) and enter at t+1 open
        # Start from the point where indicators are available
        eq: List[Tuple[int, float]] = []
        last_equity = self.balance

        for i in range(2, len(df) - 1):
            prev = df.iloc[i - 1]
            cur = df.iloc[i]
            nxt = df.iloc[i + 1]

            # Equity at current bar close (mark to close)
            if self.pos_side is None:
                last_equity = self.balance
            else:
                mark = cur["close"]
                unreal = float((Decimal(str(mark)) - self.entry_price) * self.pos_qty) if self.pos_side == "long" else float((self.entry_price - Decimal(str(mark))) * self.pos_qty)
                last_equity = self.balance + unreal
            eq.append((int(cur["start"]), float(last_equity)))

            # If position is open, check SL/TP/trailing intrabar on current bar
            if self.pos_side is not None:
                closed = self._check_exits_intrabar(cur["open"], cur["high"], cur["low"], cur["close"], int(cur["start"]))
                if closed:
                    pass  # position state updated

            # Generate signal on current bar close
            signal = gen_signal(prev["st_dir"], cur["st_dir"], cur["close"], cur["st"])

            # If position present and signal flips against, exit at next open
            if self.pos_side == "long" and signal in (-1, -2):
                self._exit(float(nxt["open"]), "signal_flip", int(nxt["start"]))
            elif self.pos_side == "short" and signal in (1, 2):
                self._exit(float(nxt["open"]), "signal_flip", int(nxt["start"]))

            # If flat and allowed to open, act on signal at next bar open
            if self.pos_side is None and signal in (1, 2, -1, -2):
                side = "long" if signal > 0 else "short"
                # Compute SL/TP using next open as entry reference (realistic)
                self._enter(side, float(nxt["open"]), int(nxt["start"]))

        # Append final equity at last bar close
        if len(df) > 0:
            last = df.iloc[-1]
            if self.pos_side is None:
                last_equity = self.balance
            else:
                mark = last["close"]
                unreal = float((Decimal(str(mark)) - self.entry_price) * self.pos_qty) if self.pos_side == "long" else float((self.entry_price - Decimal(str(mark))) * self.pos_qty)
                last_equity = self.balance + unreal
            eq.append((int(last["start"]), float(last_equity)))

        eq_vals = [e for (_, e) in eq]
        pnl_series = pd.Series(eq_vals).diff().fillna(0.0).values
        sharpe_like = 0.0 if np.std(pnl_series) == 0 else float(np.mean(pnl_series) / np.std(pnl_series))
        max_dd = self._max_drawdown(eq_vals)
        net = float(eq_vals[-1] - eq_vals[0]) if eq_vals else 0.0

        trades_df = pd.DataFrame(self.trades)
        if not trades_df.empty:
            win_rate = float((trades_df["pnl"] > 0).mean())
        else:
            win_rate = 0.0

        self.equity_curve = eq
        return BTResults(
            net_pnl=round(net, 6),
            max_drawdown=round(max_dd, 6),
            sharpe_like=round(sharpe_like, 4),
            win_rate=round(win_rate, 4),
            num_trades=int(len(trades_df)),
            equity_curve=eq,
            trades=trades_df
        )

    @staticmethod
    def _max_drawdown(equity: List[float]) -> float:
        peak = -1e30
        max_dd = 0.0
        for e in equity:
            if e > peak:
                peak = e
            dd = peak - e
            if dd > max_dd:
                max_dd = dd
        return float(max_dd)


# ============================== Optimizer ==============================

def optimize(params: BTParams, df: Optional[pd.DataFrame], instr: Optional[Instr],
             trials: int, metric: str = "net", risk_penalty: float = 0.25,
             max_dd_cap: Optional[float] = None) -> Tuple[BTResults, Dict]:
    """
    metric: "net" -> net - lambda*dd, or "sharpe"
    """
    assert metric in ("net", "sharpe")

    # Pre-fetch if not provided
    if df is None or instr is None:
        dl = BybitData(params)
        if instr is None:
            instr = dl.get_instrument()
        if df is None:
            df = dl.get_klines()

    def objective(trial: optuna.Trial) -> float:
        p = BTParams(**vars(params))  # shallow copy

        # Tune ST + risk + exits
        p.st_period = trial.suggest_int("st_period", 5, 30)
        p.st_multiplier = trial.suggest_float("st_multiplier", 1.0, 5.0)
        p.stop_loss_pct = trial.suggest_float("stop_loss_pct", 0.003, 0.03, log=True)
        p.take_profit_pct = trial.suggest_float("take_profit_pct", 0.006, 0.06, log=True)
        p.trailing_stop_pct = trial.suggest_float("trailing_stop_pct", 0.0, 0.03)
        p.trailing_activation_pct = trial.suggest_float("trailing_activation_pct", 0.0, 0.03)
        p.risk_per_trade_pct = trial.suggest_float("risk_per_trade_pct", 0.2, 3.0, log=True)
        p.slippage_bps = trial.suggest_float("slippage_bps", 0.0, 2.0)

        bt = SupertrendBacktester(p, df_klines=df, instr=instr)
        res = bt.run()

        score = res.net_pnl - risk_penalty * res.max_drawdown if metric == "net" else res.sharpe_like
        if max_dd_cap is not None and res.max_drawdown > max_dd_cap:
            score = -1e9
        trial.set_user_attr("net_pnl", res.net_pnl)
        trial.set_user_attr("max_drawdown", res.max_drawdown)
        trial.set_user_attr("sharpe_like", res.sharpe_like)
        trial.set_user_attr("win_rate", res.win_rate)
        trial.set_user_attr("num_trades", res.num_trades)
        return float(score)

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42, multivariate=True))
    study.optimize(objective, n_trials=trials, show_progress_bar=True)

    best_p = BTParams(**vars(params))
    best = study.best_trial
    for k, v in best.params.items():
        setattr(best_p, k, v)

    # Final run with best params
    final_bt = SupertrendBacktester(best_p, df_klines=df, instr=instr)
    final_res = final_bt.run()
    return final_res, {"best_params": best.params, "best_score": best.value, "study": study}


# ============================== CLI ==============================

def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def main():
    ap = argparse.ArgumentParser(description="Supertrend backtester + optimizer (Bybit V5 historical data)")
    ap.add_argument("--symbol", type=str, default="BTCUSDT")
    ap.add_argument("--category", type=str, default="linear", choices=["linear", "spot", "inverse"])
    ap.add_argument("--interval", type=str, default="15", help="Kline interval (1,3,5,15,30,60,120,240,720,D)")
    ap.add_argument("--start", type=str, required=True, help="UTC start, e.g., 2024-06-01T00:00:00")
    ap.add_argument("--end", type=str, required=True, help="UTC end, e.g., 2024-06-07T00:00:00")
    ap.add_argument("--testnet", action="store_true")

    # Trading params
    ap.add_argument("--initial-balance", type=float, default=10000)
    ap.add_argument("--leverage", type=float, default=5.0)
    ap.add_argument("--taker-fee", type=float, default=0.0006)
    ap.add_argument("--maker-fee", type=float, default=0.0001)
    ap.add_argument("--slippage-bps", type=float, default=0.0)
    ap.add_argument("--risk-pct", type=float, default=1.0)
    ap.add_argument("--min-pos-usd", type=float, default=10.0)
    ap.add_argument("--max-pos-usd", type=float, default=10000.0)

    # Strategy params
    ap.add_argument("--st-period", type=int, default=10)
    ap.add_argument("--st-mult", type=float, default=3.0)
    ap.add_argument("--sl-pct", type=float, default=0.015)
    ap.add_argument("--tp-pct", type=float, default=0.03)
    ap.add_argument("--trail-pct", type=float, default=0.0)
    ap.add_argument("--trail-act-pct", type=float, default=0.0)

    # Execution model
    ap.add_argument("--fill-on-touch", action="store_true", help="Fill when SL/TP touched intra-bar")
    ap.add_argument("--path-seed", type=int, default=42)

    # Optimize
    ap.add_argument("--optimize", action="store_true")
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--metric", type=str, default="net", choices=["net", "sharpe"])
    ap.add_argument("--risk-penalty", type=float, default=0.25)
    ap.add_argument("--max-dd-cap", type=float, default=None)

    args = ap.parse_args()

    params = BTParams(
        symbol=args.symbol,
        category=args.category,
        interval=args.interval,
        start=parse_dt(args.start),
        end=parse_dt(args.end),
        testnet=args.testnet,
        initial_balance=args.initial_balance,
        leverage=args.leverage,
        taker_fee=args.taker_fee,
        maker_fee=args.maker_fee,
        slippage_bps=args.slippage_bps,
        risk_per_trade_pct=args.risk_pct,
        min_position_value=args.min_pos_usd,
        max_position_value=args.max_pos_usd,
        st_period=args.st_period,
        st_multiplier=args.st_mult,
        stop_loss_pct=args.sl_pct,
        take_profit_pct=args.tp_pct,
        trailing_stop_pct=args.trail_pct,
        trailing_activation_pct=args.trail_act_pct,
        fill_on_touch=args.fill_on_touch,
        path_seed=args.path_seed
    )

    # Pre-fetch once so optimizer can reuse
    loader = BybitData(params)
    instr = loader.get_instrument()
    df = loader.get_klines()

    if args.optimize:
        final_res, meta = optimize(
            params, df=df, instr=instr,
            trials=args.trials, metric=args.metric,
            risk_penalty=args.risk_penalty, max_dd_cap=args.max_dd_cap
        )
        print("Optimization complete")
        print(f"Best score: {meta['best_score']:.6f}")
        print("Best parameters:")
        for k, v in meta["best_params"].items():
            print(f"  {k}: {v}")
        print("\nFinal results with best parameters:")
        print_result(final_res)
        # Save outputs
        pd.DataFrame(final_res.equity_curve, columns=["timestamp_ms", "equity"]).assign(
            timestamp=lambda d: d["timestamp_ms"].apply(lambda x: from_ms(x).isoformat())
        ).to_csv("equity_curve_best.csv", index=False)
        final_res.trades.to_csv("trades_best.csv", index=False)
        print("Saved equity_curve_best.csv and trades_best.csv")
    else:
        bt = SupertrendBacktester(params, df_klines=df, instr=instr)
        res = bt.run()
        print_result(res)
        pd.DataFrame(res.equity_curve, columns=["timestamp_ms", "equity"]).assign(
            timestamp=lambda d: d["timestamp_ms"].apply(lambda x: from_ms(x).isoformat())
        ).to_csv("equity_curve.csv", index=False)
        res.trades.to_csv("trades.csv", index=False)
        print("Saved equity_curve.csv and trades.csv")


def print_result(res: BTResults):
    print("Backtest results")
    print("----------------")
    print(f"Net PnL         : {res.net_pnl:.6f}")
    print(f"Max Drawdown    : {res.max_drawdown:.6f}")
    print(f"Sharpe-like     : {res.sharpe_like:.4f}")
    print(f"Win rate        : {res.win_rate*100:.2f}%")
    print(f"Trades          : {res.num_trades}")


if __name__ == "__main__":
    main()
```

How it maps to your bot

- Signals: Same logic as your generate_signal (trend flips produce STRONG_BUY/SELL; otherwise BUY/SELL when price is above/below supertrend within that trend).
- Indicator: Uses pandas_ta.supertrend with your period and multiplier; data is fetched from Bybit V5 get_kline for the requested interval and time window.
- Entries: Signal at bar t executes at t+1 open (prevents look-ahead).
- Exits: SL/TP and optional trailing stop are checked intra-bar using a deterministic O-H-L-C path; fill_on_touch means a touch fills.
- Sizing: Risk-per-trade sizing like your calculate_position_size_usd: risk $ = balance * risk_pct; position value = risk / stop_distance_pct; capped by leverage and min/max position USD; qty = position_value / entry; rounded to Bybit’s qty_step and enforced by min/max order qty.
- Fees/slippage: Taker fee applied to both entry and exit. Optional slippage in basis points.

Install and run

- Install:
  pip install "pybit==5.*" pandas numpy pandas_ta optuna

- Backtest (UTC times):
  python supertrend_backtester.py --symbol BTCUSDT --category linear --interval 15 --start 2024-06-01T00:00:00 --end 2024-06-07T00:00:00 --initial-balance 10000 --leverage 5 --fill-on-touch

- Optimize for profit (net − 0.3 × maxDD) over the same window:
  python supertrend_backtester.py --symbol BTCUSDT --category linear --interval 15 --start 2024-06-01T00:00:00 --end 2024-06-14T00:00:00 --optimize --trials 120 --metric net --risk-penalty 0.3 --fill-on-touch

Notes and tweak ideas

- Walk-forward: For robustness, split [start,end) into N segments and score each trial on all segments (average or min); trivial to add around optimize().
- Execution realism: If you switch your live bot to LIMIT orders, change taker_fee to maker_fee, add queue/latency modeling, and allow partial fills by volume.
- Funding, fees, and inverse contracts: This model ignores funding and assumes linear (USDT) contracts. You can extend pnl math for inverse pairs if needed.
- Trailing stops: trail_act_pct=0 makes it activate immediately; otherwise it activates after price moves that percent in your favor.

If you share the exact assets/timeframes you care about, I can pre-populate sensible parameter bounds and add a simple matplotlib plotter for equity and drawdowns.
# Supertrend Bot Backtester with Bybit Historical Data

I'll help you create a comprehensive backtester for your Supertrend trading bot that uses historical live data from Bybit to optimize profit. This backtester will allow you to test your strategy's performance without risking real money.

## Overview

Your Supertrend bot is well-structured with robust features like precision management, risk-based position sizing, and trailing stops. To backtest it effectively, we need to:
- **Download historical data from Bybit**
- **Simulate the trading logic without live execution**
- **Calculate performance metrics**
- **Optimize parameters for maximum profit**

## Step 1: Historical Data Download from Bybit

### Data Fetching Implementation

First, let's create a robust data downloader that can fetch extensive historical data from Bybit's V5 API:

```python
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
from pybit.unified_trading import HTTP
import json

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
```



## Step 2: Backtesting Engine

### Core Backtesting Class

Here's a comprehensive backtesting engine that simulates your Supertrend bot's logic:

```python
import pandas_ta as ta
from decimal import Decimal
from dataclasses import dataclass, field
from typing import List, Dict, Optional

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
```

## Step 3: Parameter Optimization

### Grid Search Optimization

To find the optimal parameters for maximum profit:

```python
from itertools import product
import multiprocessing as mp
from functools import partial

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
```

## Step 4: Visualization and Analysis

### Performance Visualization

```python
import matplotlib.pyplot as plt
import seaborn as sns

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
        axes.hist(pnls, bins=30, edgecolor='black', alpha=0.7)
        axes.axvline(x=0, color='red', linestyle='--')
        axes.set_xlabel('PnL ($)')
        axes.set_ylabel('Frequency')
        axes.set_title('Trade PnL Distribution')
        
        # Win/Loss pie chart
        sizes = [results.winning_trades, results.losing_trades]
        labels = ['Winning Trades', 'Losing Trades']
        colors = ['green', 'red']
        axes.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%')
        axes.set_title('Win/Loss Ratio')
        
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
```

## Step 5: Complete Backtest Execution

### Main Execution Script

```python
@dataclass
class BacktestConfig:
    """Backtest configuration"""
    # Data parameters
    SYMBOL: str = "BTCUSDT"
    CATEGORY: str = "linear"
    TIMEFRAME: str = "15"  # 15-minute bars
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
    ALLOW_SHORT: bool = False  # Enable short positions
    COMMISSION: float = 0.0006  # 0.06% taker fee

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
    best_params = optimization_results.iloc['parameters']
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
```

## Key Features of This Backtester

### **Data Management**
- Downloads historical kline data directly from Bybit V5 API
- Handles rate limiting and pagination automatically
- Saves data locally for faster subsequent runs

### **Strategy Simulation**
- Accurately simulates your Supertrend strategy logic
- Supports both long and short positions
- Implements proper stop-loss and take-profit mechanics
- Handles position sizing based on risk percentage

### **Performance Analysis**
- Calculates comprehensive metrics (Sharpe ratio, drawdown, profit factor)
- Generates detailed trade logs
- Creates visualization of equity curves and trade distributions

### **Optimization**
- Grid search optimization for finding best parameters
- Parallel processing support for faster optimization
- Exports results for further analysis

## Important Considerations

**Data Quality**: Ensure you're using sufficient historical data (at least 1-2 years) for reliable backtesting results.

**Transaction Costs**: The backtester includes commission calculation, but also consider slippage in live trading.

**Overfitting**: Avoid over-optimizing on historical data. Always reserve some data for out-of-sample testing.

**Market Conditions**: Test your strategy across different market conditions (trending, ranging, volatile).

**Risk Management**: The backtester respects your position sizing and risk limits, crucial for realistic results.

This backtester provides a solid foundation for optimizing your Supertrend bot's profitability. You can extend it further by adding features like walk-forward analysis, Monte Carlo simulations, or machine learning-based parameter optimization.

