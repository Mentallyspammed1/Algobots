# backtest.py
import argparse
import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from pybit.unified_trading import HTTP
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)


class BybitAPIError(Exception):
    def __init__(self, message: str, ret_code: int = -1, ret_msg: str = "Unknown"):
        super().__init__(message)
        self.ret_code = ret_code
        self.ret_msg = ret_msg


class BybitRateLimitError(BybitAPIError):
    pass


from config import Config

# Import your bot and config
from market_maker import MarketMaker  # rename if your file is different

API_SLEEP_INTERVAL = 0.05  # Sleep interval for API calls to respect rate limits

logger = logging.getLogger("Backtester")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


# -------- Utilities


def to_ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


@dataclass
class BacktestParams:
    symbol: str
    category: str = "linear"  # "linear" | "inverse" | "spot"
    interval: str = (
        "1"  # Bybit kline interval as string: "1","3","5","15","60","240","D",...
    )
    start: datetime = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end: datetime = datetime(2024, 1, 2, tzinfo=timezone.utc)
    testnet: bool = False
    # Execution model
    maker_fee: float = (
        0.0002  # 2 bps; set negative if you receive rebates (e.g., -0.00025)
    )
    fill_on_touch: bool = True  # fill if price touches order
    volume_cap_ratio: float = 0.25  # cap fills to a fraction of candle volume (0..1)
    rng_seed: int = 42  # for deterministic intra-candle path
    sl_tp_emulation: bool = (
        True  # emulate SL/TP using Config STOP_LOSS_PCT / TAKE_PROFIT_PCT
    )


class BybitHistoricalData:
    """
    Pulls historical klines via Bybit v5 public API using pybit.
    """

    def __init__(self, params: BacktestParams):
        self.params = params
        # For public endpoints, keys are optional
        self.http = HTTP(testnet=params.testnet)
        self.logger = logging.getLogger("Backtester")  # Use the existing logger
        self._api_retry = (
            self._get_api_retry_decorator()
        )  # Initialize the decorator here

    def _is_retryable_bybit_error(self, exception: Exception) -> bool:
        if not isinstance(exception, BybitAPIError):
            return False
        # Only retry on rate limits for now
        if isinstance(exception, (BybitRateLimitError,)):
            return True
        return False

    def _get_api_retry_decorator(self):
        # Define retry parameters (can be made configurable in BacktestParams if needed)
        api_retry_attempts = 5
        api_retry_initial_delay_sec = 1.0
        api_retry_max_delay_sec = 10.0

        return retry(
            stop=stop_after_attempt(api_retry_attempts),
            wait=wait_exponential_jitter(
                initial=api_retry_initial_delay_sec,
                max=api_retry_max_delay_sec,
            ),
            retry=retry_if_exception(self._is_retryable_bybit_error),
            before_sleep=before_sleep_log(self.logger, logging.WARNING, exc_info=False),
            reraise=True,
        )

    @property
    def get_klines(self) -> Callable[[], pd.DataFrame]:
        # This property returns the decorated get_klines method
        return self._api_retry(self._get_klines_impl)

    def _get_klines_impl(self) -> pd.DataFrame:
        """
        Fetch klines over [start, end) range, handling pagination (limit=1000 bars).
        Returns DataFrame sorted by start time with columns:
        ['start', 'open', 'high', 'low', 'close', 'volume', 'turnover']
        All price columns are floats; 'start' is int ms.
        """
        start_ms = to_ms(self.params.start)
        end_ms = to_ms(self.params.end)
        all_rows: list[list[str]] = []
        limit = 1000

        while True:
            try:
                resp = self.http.get_kline(
                    category=self.params.category,
                    symbol=self.params.symbol,
                    interval=self.params.interval,
                    start=start_ms,
                    end=end_ms,
                    limit=limit,
                )
            except Exception as e:  # Catch any exception from pybit's get_kline
                # Check if it's a rate limit error or other API error
                if (
                    hasattr(e, "status_code") and e.status_code == 429
                ):  # Common rate limit status code
                    raise BybitRateLimitError(f"API rate limit hit: {e}")
                elif hasattr(
                    e, "message"
                ):  # pybit errors often have a 'message' attribute
                    raise BybitAPIError(
                        f"Bybit API error: {e.message}", ret_msg=e.message
                    )
                else:
                    raise BybitAPIError(f"Unknown API error: {e}")

            ret_code = resp.get("retCode")
            ret_msg = resp.get("retMsg", "Unknown error")

            if ret_code == 10006:  # Specific Bybit rate limit error code
                raise BybitRateLimitError(
                    f"Bybit get_kline rate limit: {ret_msg}",
                    ret_code=ret_code,
                    ret_msg=ret_msg,
                )
            elif ret_code != 0:
                raise BybitAPIError(
                    f"Bybit get_kline error: {ret_msg}",
                    ret_code=ret_code,
                    ret_msg=ret_msg,
                )

            rows = resp["result"]["list"]
            if not rows:
                break

            # Bybit returns list of lists as strings:
            # [start, open, high, low, close, volume, turnover]
            # Some SDK versions return newest->oldest; sort when appending.
            rows_sorted = sorted(rows, key=lambda r: int(r[0]))
            all_rows.extend(rows_sorted)

            # Advance start_ms for pagination
            last_ms = int(rows_sorted[-1][0])
            # Prevent infinite loop
            next_ms = last_ms + 1
            if next_ms >= end_ms:
                break
            start_ms = next_ms

            # Removed time.sleep(API_SLEEP_INTERVAL) as tenacity handles delays

        if not all_rows:
            raise ValueError("No klines returned for the requested range.")

        df = pd.DataFrame(
            all_rows,
            columns=["start", "open", "high", "low", "close", "volume", "turnover"],
        )
        for col in ["start"]:
            df[col] = df[col].astype(np.int64)
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            df[col] = df[col].astype(float)

        df = df.sort_values("start").reset_index(drop=True)
        return df


class FillEngine:
    """
    Simulates maker fills within a candle using intra-candle price path approximation.
    It manages order fills based on available volume capacity and price touch logic.
    """

    def __init__(self, params: BacktestParams):
        self.params = params
        random.seed(params.rng_seed)

    def _intrabar_path(
        self, o: float, h: float, low_price: float, c: float, ts_ms: int
    ) -> list[float]:
        """
        Generate a simple deterministic intra-candle path: open -> mid-extreme ->
        other extreme -> close. The ordering (O-H-L-C) vs (O-L-H-C) is seeded by
        timestamp for variety but reproducibility.
        """
        rnd = (ts_ms // 60000) ^ self.params.rng_seed
        go_high_first = rnd % 2 == 0
        if go_high_first:
            return [
                o,
                (o + h) / 2,
                h,
                (h + low_price) / 2,
                low_price,
                (low_price + c) / 2,
                c,
            ]
        else:
            return [
                o,
                (o + low_price) / 2,
                low_price,
                (low_price + h) / 2,
                h,
                (h + c) / 2,
                c,
            ]

    def _volume_capacity(self, candle_volume: float) -> float:
        """
        Simplistic capacity: only a fraction of the candle's volume is available
        to our maker orders. Interpreting 'volume' as contract or base-asset
        volume depending on market; adjust as needed.
        """
        return max(0.0, candle_volume) * self.params.volume_cap_ratio

    def simulate_fills_for_step(
        self, mm: MarketMaker, krow: pd.Series
    ) -> dict[str, float]:
        """
        Apply fills to mm.active_orders for this kline step.
        Returns dict with aggregate 'filled_buy' and 'filled_sell' notional sizes for logging/debug.
        """
        o, h, low_price, c = krow.open, krow.high, krow.low, krow.close
        ts_ms = int(krow.start)
        path = self._intrabar_path(o, h, low_price, c, ts_ms)

        capacity_remaining = self._volume_capacity(krow.volume)

        filled_buy = 0.0
        filled_sell = 0.0

        # Snapshot orders at start of step
        buy_orders = list(mm.active_orders.get("buy", {}).items())
        sell_orders = list(mm.active_orders.get("sell", {}).items())

        # Fill-on-touch logic
        def path_touches_or_crosses(target_price: float, side: str) -> bool:
            if not self.params.fill_on_touch:
                return False
            # If buy, we need low <= bid; if sell, high >= ask
            if side == "buy":
                return min(path) <= target_price
            else:
                return max(path) >= target_price

        # Fills are price-time: we assume our orders rest the whole step.
        # Capacity is shared across all orders within the step.
        # You can enhance to prioritize better prices first, etc.
        # Buy orders
        for oid, od in buy_orders:
            if capacity_remaining <= 0:
                break
            price = float(od["price"])
            size = float(od["size"])
            if path_touches_or_crosses(price, "buy"):
                fill_size = min(size, capacity_remaining)
                pnl_delta, pos_delta, new_avg = self._apply_fill(
                    mm, side="Buy", price=price, size=fill_size
                )
                capacity_remaining -= fill_size
                filled_buy += fill_size
                # Remove/adjust order
                if fill_size >= size - 1e-12:
                    del mm.active_orders["buy"][oid]
                else:
                    mm.active_orders["buy"][oid]["size"] = size - fill_size

        # Sell orders
        for oid, od in sell_orders:
            if capacity_remaining <= 0:
                break
            price = float(od["price"])
            size = float(od["size"])
            if path_touches_or_crosses(price, "sell"):
                fill_size = min(size, capacity_remaining)
                pnl_delta, pos_delta, new_avg = self._apply_fill(
                    mm, side="Sell", price=price, size=fill_size
                )
                capacity_remaining -= fill_size
                filled_sell += fill_size
                # Remove/adjust order
                if fill_size >= size - 1e-12:
                    del mm.active_orders["sell"][oid]
                else:
                    mm.active_orders["sell"][oid]["size"] = size - fill_size

        # Optional: SL/TP emulation for open inventory based on avg_entry
        if self.params.sl_tp_emulation and mm.position != 0 and mm.avg_entry_price:
            if mm.position > 0:
                stop = mm.avg_entry_price * (1 - mm.config.STOP_LOSS_PCT)
                tp = mm.avg_entry_price * (1 + mm.config.TAKE_PROFIT_PCT)
                # If stop or TP touched intra-bar, close up to |position|
                close_here = None
                if min(path) <= stop:
                    close_here = stop
                elif max(path) >= tp:
                    close_here = tp
                if close_here is not None:
                    self._apply_close_all(mm, price=close_here)
            else:
                stop = mm.avg_entry_price * (1 + mm.config.STOP_LOSS_PCT)
                tp = mm.avg_entry_price * (1 - mm.config.TAKE_PROFIT_PCT)
                close_here = None
                if max(path) >= stop:
                    close_here = stop
                elif min(path) <= tp:
                    close_here = tp
                if close_here is not None:
                    self._apply_close_all(mm, price=close_here)

        # Update last/mid to close of candle for next step
        mm.last_price = c
        mm.mid_price = c

        return {"filled_buy": filled_buy, "filled_sell": filled_sell}

    def _calculate_fill_pnl_and_position_update(
        self,
        mm: MarketMaker,
        pos_before: float,
        avg_before: float,
        side: str,
        pos_delta: float,
        price: float,
    ) -> float:
        realized_pnl_delta = 0.0
        if pos_before == 0 or np.sign(pos_before) == np.sign(pos_delta):
            # Adding to same-direction inventory
            new_pos = pos_before + pos_delta
            new_avg = ((abs(pos_before) * avg_before) + (abs(pos_delta) * price)) / max(
                abs(new_pos), 1e-12
            )
            mm.position = new_pos
            mm.avg_entry_price = new_avg
        else:
            # Reducing or flipping
            if abs(pos_delta) <= abs(pos_before):
                # Partial or full reduction
                closed = abs(pos_delta)
                realized_pnl_delta = self._closed_pnl(
                    side, entry=avg_before, fill=price, qty=closed
                )
                new_pos = pos_before + pos_delta
                mm.position = new_pos
                mm.avg_entry_price = avg_before if new_pos != 0 else 0.0
            else:
                # Flip: close old, open new in opposite direction
                closed = abs(pos_before)
                realized_pnl_delta = self._closed_pnl(
                    side, entry=avg_before, fill=price, qty=closed
                )
                leftover = abs(pos_delta) - closed
                new_side_delta = np.sign(pos_delta) * leftover
                mm.position = new_side_delta
                mm.avg_entry_price = price
        return realized_pnl_delta

    def _apply_fill(
        self, mm: MarketMaker, side: str, price: float, size: float
    ) -> tuple[float, float, float]:
        """
        Apply a trade fill to MarketMaker state. Returns (realized_pnl_delta,
        position_delta, new_avg_entry). Fee is charged on notional.
        """
        # Fee on notional (maker)
        fee = abs(price * size) * self.params.maker_fee

        pos_before = mm.position
        avg_before = mm.avg_entry_price or 0.0

        pos_delta = size if side.lower() == "buy" else -size
        realized_pnl_delta = self._calculate_fill_pnl_and_position_update(
            mm, pos_before, avg_before, side, pos_delta, price
        )

        # Accrue fees into realized pnl
        mm.unrealized_pnl = (
            (mm.last_price - mm.avg_entry_price) * mm.position
            if mm.position != 0
            else 0.0
        )
        mm.realized_pnl += realized_pnl_delta - abs(fee)

        return realized_pnl_delta - abs(fee), pos_delta, mm.avg_entry_price

    def _apply_close_all(self, mm: MarketMaker, price: float):
        """
        Close entire position at given price (used for SL/TP emulation).
        """
        if mm.position == 0:
            return
        side = "Sell" if mm.position > 0 else "Buy"
        qty = abs(mm.position)
        # Realized PnL on close
        realized = self._closed_pnl(side, entry=mm.avg_entry_price, fill=price, qty=qty)
        fee = abs(price * qty) * self.params.maker_fee
        mm.realized_pnl += realized - abs(fee)
        mm.position = 0.0
        mm.avg_entry_price = 0.0
        mm.unrealized_pnl = 0.0
        # Cancel any resting orders (we just closed the book)
        mm.active_orders = {"buy": {}, "sell": {}}

    @staticmethod
    def _closed_pnl(exec_side: str, entry: float, fill: float, qty: float) -> float:
        """
        Realized PnL for closing qty units.
        If we execute a Sell, we are closing a long. If we execute a Buy, we are closing a short.
        """
        if exec_side.lower() == "sell":  # closing long
            return (fill - entry) * qty
        else:  # buy closes short
            return (entry - fill) * qty


class MarketMakerBacktester:
    """
    Orchestrates the backtesting process for the MarketMaker bot.
    It fetches historical data, simulates fills, and calculates performance metrics.
    """

    def __init__(self, params: BacktestParams, cfg: Config | None = None):
        self.params = params
        self.cfg = cfg or Config()
        self.data = BybitHistoricalData(params)
        self.fill_engine = FillEngine(params)

        # Bot under test
        self.mm = MarketMaker()
        print(f"MarketMaker imported from: {MarketMaker.__file__}")
        import sys

        print(f"sys.path: {sys.path}")
        # Force backtest mode (no session) but keep config and symbol/category consistent
        self.mm.session = None
        self.mm.config.SYMBOL = params.symbol
        self.mm.config.CATEGORY = params.category

        # Metrics
        self.equity_curve: list[tuple[int, float]] = []  # (timestamp ms, equity)
        self.drawdowns: list[float] = []
        self.trades: list[dict] = []  # optional detailed trade log

    def run(self) -> dict[str, float]:
        klines = self.data.get_klines()

        # Initialize prices with first candle open
        first = klines.iloc[0]
        self.mm.last_price = first.open
        self.mm.mid_price = first.open

        # Track equity; assume starting cash (USDT) is implicit 0 and PnL purely from trading.
        # If you want to start with specific cash, add it here and include fees accordingly.

        for _idx, row in klines.iterrows():
            # 1) Let bot update/cancel/place orders based on current mid
            self.mm.update_orders()

            # 2) Simulate fills within this step
            self.fill_engine.simulate_fills_for_step(self.mm, row)

            # 3) Compute equity at close of step
            equity = self.mm.realized_pnl + self._unrealized(self.mm, mark=row.close)
            self.equity_curve.append((int(row.start), equity))

        # Final metrics
        equity_series = pd.Series([e for (_, e) in self.equity_curve])
        returns = equity_series.diff().fillna(0.0)
        # If you want per-step percentage returns, divide by a notional NAV; here we use 1 as base.
        sharpe = self._calc_sharpe(returns.values)

        total_return = float(equity_series.iloc[-1]) if len(equity_series) > 0 else 0.0
        max_dd = self._max_drawdown([e for (_, e) in self.equity_curve])

        result = {
            "net_pnl": round(total_return, 6),
            "max_drawdown": round(max_dd, 6),
            "sharpe_like": round(sharpe, 4),
            "final_position": float(self.mm.position),
        }
        return result

    @staticmethod
    def _unrealized(mm: MarketMaker, mark: float) -> float:
        if mm.position == 0:
            return 0.0
        return (mark - mm.avg_entry_price) * mm.position

    @staticmethod
    def _calc_sharpe(step_pnl: np.ndarray) -> float:
        if len(step_pnl) < 2:
            return 0.0
        mu = np.mean(step_pnl)
        sd = np.std(step_pnl)
        if sd == 0:
            return 0.0
        # This is a per-step Sharpe proxy (no annualization here). Adjust as desired.
        return float(mu / sd)

    @staticmethod
    def _max_drawdown(equity: list[float]) -> float:
        peak = -float("inf")
        max_dd = 0.0
        for e in equity:
            if e > peak:
                peak = e
            dd = peak - e
            if dd > max_dd:
                max_dd = dd
        return max_dd


def main():
    parser = argparse.ArgumentParser(
        description="Backtest MarketMaker with Bybit historical data."
    )
    parser.add_argument("--symbol", type=str, default="BTCUSDT")
    parser.add_argument(
        "--category", type=str, default="linear", choices=["linear", "inverse", "spot"]
    )
    parser.add_argument(
        "--interval",
        type=str,
        default="1",
        help="Bybit kline interval: 1,3,5,15,60,240,D,...",
    )
    parser.add_argument(
        "--start", type=str, required=True, help="UTC start, e.g. 2024-06-01T00:00:00"
    )
    parser.add_argument(
        "--end", type=str, required=True, help="UTC end, e.g. 2024-06-07T00:00:00"
    )
    parser.add_argument("--testnet", action="store_true", help="Use Bybit testnet")
    parser.add_argument("--maker_fee", type=float, default=0.0002)
    parser.add_argument("--volume_cap_ratio", type=float, default=0.25)
    parser.add_argument(
        "--no_sl_tp", action="store_true", help="Disable SL/TP emulation"
    )
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)

    params = BacktestParams(
        symbol=args.symbol,
        category=args.category,
        interval=args.interval,
        start=start,
        end=end,
        testnet=args.testnet,
        maker_fee=args.maker_fee,
        volume_cap_ratio=args.volume_cap_ratio,
        sl_tp_emulation=not args.no_sl_tp,
    )

    bt = MarketMakerBacktester(params)
    results = bt.run()

    # Pretty print
    print("Backtest results")
    print("----------------")
    for k, v in results.items():
        print(f"{k:16s}: {v}")

    # Optional: save equity curve
    df_eq = pd.DataFrame(bt.equity_curve, columns=["timestamp_ms", "equity"])
    df_eq["timestamp"] = df_eq["timestamp_ms"].apply(lambda x: from_ms(x).isoformat())
    df_eq.to_csv("equity_curve.csv", index=False)
    print("Saved equity_curve.csv")


if __name__ == "__main__":
    main()
