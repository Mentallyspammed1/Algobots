# backtest.py
import math
import time
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    # pybit unified v5
    from pybit.unified_trading import HTTP
except Exception:
    HTTP = None  # we will fall back to plain requests if needed

import requests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ---------- Utilities ----------

def to_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def interval_to_ms(interval: str) -> int:
    # Bybit v5 intervals: '1','3','5','15','30','60','120','240','360','720','D','W','M'
    if interval.isdigit():
        return int(interval) * 60_000
    if interval == 'D':
        return 24 * 60 * 60_000
    if interval == 'W':
        return 7 * 24 * 60 * 60_000
    if interval == 'M':
        # Use 30-day month to chunk pagination; exact month length isn’t required for paging
        return 30 * 24 * 60 * 60_000
    raise ValueError(f"Unsupported interval: {interval}")


def floor_to_step(x: float, step: float) -> float:
    if step <= 0:
        return x
    return math.floor(x / step) * step


def round_to_step(x: float, step: float) -> float:
    if step <= 0:
        return x
    return round(round(x / step) * step, 12)


# ---------- Data Loader (Bybit v5 Klines) ----------

class BybitKlineLoader:
    """
    Fetch historical klines (OHLCV) from Bybit v5 /market/kline.

    Sorting: Bybit returns klines in reverse order per page. We normalize to ascending by open time.
    Docs: https://bybit-exchange.github.io/docs/v5/market/kline
    """
    BASE = {
        False: "https://api.bybit.com",
        True: "https://api-testnet.bybit.com",
    }

    def __init__(self, testnet: bool, category: str, symbol: str, interval: str):
        self.testnet = testnet
        self.category = category
        self.symbol = symbol
        self.interval = interval

        self.http = None
        if HTTP is not None:
            try:
                # Public market data needs no keys
                self.http = HTTP(testnet=self.testnet, recv_window=5000)
            except Exception as e:
                logger.warning(f"pybit HTTP init failed, will fallback to requests: {e}")

    def _get_kline(self, start_ms: Optional[int], end_ms: Optional[int], limit: int = 1000) -> Dict:
        params = {
            "category": self.category,  # linear, inverse, spot
            "symbol": self.symbol,
            "interval": self.interval,
            "limit": str(limit),
        }
        if start_ms is not None:
            params["start"] = str(start_ms)
        if end_ms is not None:
            params["end"] = str(end_ms)

        if self.http:
            return self.http.get_kline(**params)
        else:
            url = f"{self.BASE[self.testnet]}/v5/market/kline"
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()

    def load(self, start: datetime, end: datetime, limit_per_req: int = 1000) -> pd.DataFrame:
        """
        Page forward from start to end, honoring Bybit limit per request.
        """
        start_ms = to_ms(start)
        end_ms = to_ms(end)
        step = interval_to_ms(self.interval)

        rows: List[List[str]] = []
        cursor = start_ms
        while cursor <= end_ms:
            # Request a chunk [cursor, chunk_end]
            chunk_end = min(cursor + step * (limit_per_req - 1), end_ms)
            data = self._get_kline(start_ms=cursor, end_ms=chunk_end, limit=limit_per_req)
            if data.get("retCode") != 0:
                raise RuntimeError(f"Bybit get_kline error: {data.get('retMsg')}")

            lst = data.get("result", {}).get("list", [])
            if not lst:
                # No more data
                break

            # Bybit returns reverse sorted; gather then advance cursor
            rows.extend(lst)
            # Advance by exactly number of bars fetched
            earliest = int(lst[-1][0])  # last element is earliest bar start when reverse sorted
            latest = int(lst[0][0])     # first element is latest bar start
            # Next cursor is latest + step
            cursor = latest + step

            # Be gentle on rate limits
            time.sleep(0.02)

        if not rows:
            return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])

        # Normalize ascending by open time
        df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume", "turnover"])
        df = df[["open_time", "open", "high", "low", "close", "volume"]].copy()
        for col in ["open_time"]:
            df[col] = df[col].astype("int64")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype("float64")

        df.sort_values("open_time", inplace=True)
        df["open_dt"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df.set_index("open_dt", inplace=True)
        return df


# ---------- Execution bookkeeping ----------

@dataclass
class Fill:
    ts: pd.Timestamp
    side: str        # 'Buy' or 'Sell'
    price: float
    qty: float
    fee: float
    maker: bool


class ExecutionBook:
    def __init__(self, maker_fee: float = 0.0001, taker_fee: float = 0.0006):
        self.fills: List[Fill] = []
        self.realized_pnl: float = 0.0

    def record(self, fill: Fill):
        self.fills.append(fill)

    def realized(self) -> float:
        return self.realized_pnl


# ---------- Backtester ----------

class MarketMakerBacktester:
    """
    Bar-by-bar backtester for your MarketMaker class.

    Mechanics:
    - At t0, set bot.mid/last to first bar close and call bot.update_orders() to seed orders.
    - For each subsequent bar:
        1) Check fills for EXISTING orders vs that bar’s high/low.
        2) Update mark (mid/last) to bar close.
        3) Call bot.update_orders() to cancel/replace for next bar.
    """

    def __init__(
        self,
        bot,                              # your MarketMaker instance
        klines: pd.DataFrame,             # DataFrame from BybitKlineLoader.load()
        initial_cash: float = 10_000.0,
        maker_fee: float = 0.0001,        # adjust if needed
        taker_fee: float = 0.0006,        # adjust if needed
        slippage_bps: float = 0.0,        # 1 bps = 0.01%
        price_step: float = 0.01,         # optional; use instrument info for exact tick size
        qty_step: float = 0.0001,         # optional; use instrument info for exact lot size
    ):
        self.bot = bot
        self.df = klines
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.slippage_bps = slippage_bps
        self.price_step = price_step
        self.qty_step = qty_step

        self.execs = ExecutionBook(maker_fee=maker_fee, taker_fee=taker_fee)

        # Portfolio tracking
        self.equity_curve = []   # list of (timestamp, equity, position, price)
        self.max_equity = initial_cash
        self.max_dd = 0.0

        # Ensure bot runs in backtest mode (no session)
        self.bot.session = None
        self.bot.active_orders = {'buy': {}, 'sell': {}}
        self.bot.position = 0.0
        self.bot.avg_entry_price = 0.0
        self.bot.unrealized_pnl = 0.0

    # --- core math ---

    def _apply_slippage(self, price: float, side: str) -> float:
        if self.slippage_bps <= 0:
            return price
        slip = price * (self.slippage_bps / 10_000)
        if side.lower() == "buy":
            return price + slip
        else:
            return price - slip

    def _fill_one(self, ts: pd.Timestamp, side: str, price: float, qty: float, maker: bool = True):
        price = round_to_step(price, self.price_step)
        qty = round_to_step(qty, self.qty_step)
        if qty <= 0:
            return

        fee_rate = self.maker_fee if maker else self.taker_fee
        fee = abs(price * qty) * fee_rate
        self.execs.record(Fill(ts=ts, side=side, price=price, qty=qty, fee=fee, maker=maker))

        # Position/PnL accounting
        pos = self.bot.position
        avg = self.bot.avg_entry_price or 0.0

        if side.lower() == "buy":
            # closing short first
            if pos < 0:
                close_qty = min(abs(pos), qty)
                realized = (avg - price) * close_qty  # short profit = (avg - fill)*qty
                self.execs.realized_pnl += realized - fee
                pos += close_qty  # pos less negative
                qty -= close_qty
                if pos == 0:
                    avg = 0.0  # flat after closing short

            # open/increase long
            if qty > 0:
                new_pos = pos + qty
                if pos > 0:
                    avg = (avg * pos + price * qty) / new_pos
                elif pos == 0:
                    avg = price
                pos = new_pos

        else:  # sell
            # closing long first
            if pos > 0:
                close_qty = min(pos, qty)
                realized = (price - avg) * close_qty
                self.execs.realized_pnl += realized - fee
                pos -= close_qty
                qty -= close_qty
                if pos == 0:
                    avg = 0.0

            # open/increase short
            if qty > 0:
                new_pos = pos - qty
                if pos < 0:
                    # average short entry
                    avg = (avg * abs(pos) + price * qty) / abs(new_pos)
                elif pos == 0:
                    avg = price
                pos = new_pos

        self.bot.position = pos
        self.bot.avg_entry_price = avg

    def _mark_to_market(self, close_price: float):
        pos = self.bot.position
        avg = self.bot.avg_entry_price or 0.0
        if pos == 0:
            self.bot.unrealized_pnl = 0.0
            return
        if pos > 0:
            self.bot.unrealized_pnl = (close_price - avg) * pos
        else:
            self.bot.unrealized_pnl = (avg - close_price) * abs(pos)

    # --- simulation ---

    def _process_fills_for_bar(self, row: pd.Series, ts: pd.Timestamp):
        """
        Fill existing orders against current bar's high/low.
        """
        high = float(row["high"])
        low = float(row["low"])

        # BUY orders fill if low <= price
        to_remove = []
        for oid, od in list(self.bot.active_orders.get('buy', {}).items()):
            px, sz = float(od['price']), float(od['size'])
            if low <= px <= high:
                fpx = self._apply_slippage(px, "buy")
                self._fill_one(ts, "Buy", fpx, sz, maker=True)
                to_remove.append(("buy", oid))

        # SELL orders fill if high >= price
        for oid, od in list(self.bot.active_orders.get('sell', {}).items()):
            px, sz = float(od['price']), float(od['size'])
            if low <= px <= high:
                fpx = self._apply_slippage(px, "sell")
                self._fill_one(ts, "Sell", fpx, sz, maker=True)
                to_remove.append(("sell", oid))

        for side, oid in to_remove:
            # remove filled orders
            if oid in self.bot.active_orders[side]:
                del self.bot.active_orders[side][oid]

    def _record_equity(self, ts: pd.Timestamp, mark: float):
        equity = self.initial_cash + self.execs.realized_pnl + self.bot.unrealized_pnl
        self.equity_curve.append((ts, equity, self.bot.position, mark))
        self.max_equity = max(self.max_equity, equity)
        dd = (self.max_equity - equity) / self.max_equity if self.max_equity > 0 else 0.0
        self.max_dd = max(self.max_dd, dd)

    def run(self) -> pd.DataFrame:
        """
        Returns a DataFrame with equity curve and per-bar state.
        """
        if self.df.empty:
            raise ValueError("No data in klines DataFrame.")

        # Seed: use first bar close to place initial orders
        first = self.df.iloc[0]
        first_close = float(first["close"])
        self.bot.last_price = first_close
        self.bot.mid_price = first_close
        self.bot.orderbook = {"bid": [(first_close * 0.999, 1.0)], "ask": [(first_close * 1.001, 1.0)]}

        # Initial order placement
        self.bot.update_orders()
        self._mark_to_market(first_close)
        self._record_equity(self.df.index[0], first_close)

        # Iterate bars 1..N-1
        for i in range(1, len(self.df)):
            row = self.df.iloc[i]
            ts = self.df.index[i]
            close_px = float(row["close"])

            # 1) fill existing orders vs this bar
            self._process_fills_for_bar(row, ts)

            # 2) mark to market at close, update bot market state
            self.bot.last_price = close_px
            self.bot.mid_price = close_px
            # Simple synthetic top-of-book around close
            self.bot.orderbook = {"bid": [(close_px * 0.9995, 1.0)], "ask": [(close_px * 1.0005, 1.0)]}

            self._mark_to_market(close_px)
            self._record_equity(ts, close_px)

            # 3) ask bot to cancel/replace new orders for next bar
            self.bot.update_orders()

        ec = pd.DataFrame(self.equity_curve, columns=["ts", "equity", "position", "mark"])
        ec.set_index("ts", inplace=True)

        summary = {
            "initial_cash": self.initial_cash,
            "final_equity": float(ec["equity"].iloc[-1]),
            "return_pct": (float(ec["equity"].iloc[-1]) / self.initial_cash - 1) * 100.0,
            "max_drawdown_pct": self.max_dd * 100.0,
            "realized_pnl": self.execs.realized_pnl,
            "ending_position": self.bot.position,
            "ending_avg_entry": self.bot.avg_entry_price,
            "bars": len(self.df),
        }
        logger.info("Backtest summary: %s", json.dumps(summary, indent=2))
        return ec


# ---------- Convenience runner ----------

def run_backtest(
    bot,
    category: str,
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    testnet: bool = False,
    initial_cash: float = 10_000.0,
    maker_fee: float = 0.0001,
    taker_fee: float = 0.0006,
    slippage_bps: float = 0.0,
) -> pd.DataFrame:
    loader = BybitKlineLoader(testnet=testnet, category=category, symbol=symbol, interval=interval)
    df = loader.load(start=start, end=end)
    logger.info(f"Loaded {len(df)} bars for {symbol} {interval} from {start} to {end}")
    bt = MarketMakerBacktester(
        bot=bot,
        klines=df,
        initial_cash=initial_cash,
        maker_fee=maker_fee,
        taker_fee=taker_fee,
        slippage_bps=slippage_bps,
    )
    equity_curve = bt.run()
    return equity_curve
