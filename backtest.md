Awesome, you already have good “offline” hooks in your MarketMaker (session is None) that we can leverage. Below is a drop‑in backtester that:

- Pulls historical candles directly from Bybit (v5 /market/kline) via pybit
- Replays them bar‑by‑bar, feeding your bot synthetic mid/bbo, and simulates maker fills whenever a bar trades through your limit price
- Tracks position, average price, realized/unrealized PnL, equity curve, drawdown, and basic summary stats

Notes
- This is a bar-based simulator (fast, robust). If a bar’s low ≤ buy price, we assume your buy maker order fills during that bar (same for sells with high ≥ price). You can tighten this with partial/volume-limited fills if you want.
- You can switch interval to 1m for a finer replay; for true orderbook-level backtests you’d need recorded L2/trade data. Bybit offers recent trades via /v5/market/recent-trade and full trade archives for download, but not historical orderbook via REST. 

backtest.py
Copy this file alongside your MarketMaker and Config. It expects your Config to define CATEGORY, SYMBOL, TESTNET, etc., same as your bot.

```python
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
```

Example usage
Put this in a small script (run_backtest_example.py):

```python
import asyncio
from datetime import datetime, timezone, timedelta

from backtest import run_backtest
from your_module_with_bot import MarketMaker   # adjust import

if __name__ == "__main__":
    bot = MarketMaker()  # Uses your Config; session set to None by backtester

    start = datetime(2025, 7, 1, tzinfo=timezone.utc)
    end   = datetime(2025, 7, 15, tzinfo=timezone.utc)

    ec = run_backtest(
        bot=bot,
        category=bot.config.CATEGORY,   # e.g., "linear" for USDT perps
        symbol=bot.config.SYMBOL,       # e.g., "BTCUSDT"
        interval="1",                   # 1-minute klines
        start=start,
        end=end,
        testnet=bot.config.TESTNET,
        initial_cash=10_000.0,
        maker_fee=0.0001,               # adjust per your fee tier
        taker_fee=0.0006,
        slippage_bps=0.0,
    )

    print(ec.tail())
    print("Final equity:", ec['equity'].iloc[-1])
```

Optional improvements
- Enforce instrument tick/lot sizes by fetching /v5/market/instruments-info once and setting price_step/qty_step accordingly so order prices and sizes match Bybit filters. 
- Use mark or index kline for marking instead of last-trade close if desired. 
- Add partial fills using bar volume or trade counts; recent trades endpoint is available for short windows and archives for longer spans. 

Why this matches Bybit’s data model
- Historical klines are the officially supported way to pull “live historical data” programmatically via v5 /market/kline (intervals 1m to 1M). 
- Pybit’s unified_trading.HTTP exposes get_kline, which aligns with v5. Example return shape (result.list with start/open/high/low/close/volume) is the same as in the docs. 

Want me to add instrument-info rounding, partial fills, or a quick plot of the equity curve and drawdown?# Backtester for Bybit Market Maker Bot

I'll create a comprehensive backtester for your Bybit market maker bot that uses live historical data from Bybit. This backtester will simulate your trading strategy against real market data to evaluate performance before deploying it live.

## Complete Backtester Implementation

Here's a full backtesting framework that integrates with your existing MarketMaker class:

```python
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from pybit.unified_trading import HTTP
import json
from dataclasses import dataclass, asdict
import csv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class BacktestConfig:
    """Backtesting configuration parameters"""
    SYMBOL: str = "BTCUSDT"
    CATEGORY: str = "linear"  # spot, linear, inverse
    INITIAL_CAPITAL: float = 10000.0
    START_DATE: str = "2024-01-01"
    END_DATE: str = "2024-01-31"
    INTERVAL: str = "1"  # 1, 3, 5, 15, 30, 60, 120, 240, 360, 720 minutes
    MAKER_FEE: float = 0.0002  # 0.02%
    TAKER_FEE: float = 0.0005  # 0.05%
    SLIPPAGE: float = 0.0001  # 0.01%
    USE_ORDERBOOK: bool = True
    ORDERBOOK_DEPTH: int = 50

@dataclass
class Trade:
    """Trade record for backtesting"""
    timestamp: datetime
    side: str
    price: float
    quantity: float
    fee: float
    pnl: float = 0
    position_after: float = 0
    balance_after: float = 0

class BybitDataFetcher:
    """Fetches historical data from Bybit"""
    
    def __init__(self, testnet: bool = False):
        self.session = HTTP(testnet=testnet)
        
    def fetch_klines(self, symbol: str, interval: str, start_time: int, end_time: int, category: str = "linear") -> pd.DataFrame:
        """Fetch historical kline/candlestick data from Bybit"""
        all_klines = []
        current_end = end_time
        
        while current_end > start_time:
            try:
                response = self.session.get_kline(
                    category=category,
                    symbol=symbol,
                    interval=interval,
                    start=start_time,
                    end=current_end,
                    limit=1000
                )
                
                if response['retCode'] == 0:
                    klines = response['result']['list']
                    if not klines:
                        break
                    
                    all_klines.extend(klines)
                    # Update current_end to the timestamp of the oldest kline
                    current_end = int(klines[-1]) - 1
                    
                    logger.info(f"Fetched {len(klines)} klines, total: {len(all_klines)}")
                else:
                    logger.error(f"Failed to fetch klines: {response['retMsg']}")
                    break
                    
            except Exception as e:
                logger.error(f"Error fetching klines: {e}")
                break
        
        if all_klines:
            df = pd.DataFrame(all_klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
            df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                df[col] = df[col].astype(float)
            df = df.sort_values('timestamp').reset_index(drop=True)
            return df
        
        return pd.DataFrame()
    
    def fetch_orderbook_snapshot(self, symbol: str, category: str = "linear", limit: int = 50) -> Dict:
        """Fetch current orderbook snapshot"""
        try:
            response = self.session.get_orderbook(
                category=category,
                symbol=symbol,
                limit=limit
            )
            if response['retCode'] == 0:
                return response['result']
            else:
                logger.error(f"Failed to fetch orderbook: {response['retMsg']}")
                return {}
        except Exception as e:
            logger.error(f"Error fetching orderbook: {e}")
            return {}

class BacktestEngine:
    """Main backtesting engine"""
    
    def __init__(self, market_maker, config: BacktestConfig):
        self.market_maker = market_maker
        self.config = config
        self.data_fetcher = BybitDataFetcher()
        
        # Performance tracking
        self.initial_capital = config.INITIAL_CAPITAL
        self.balance = config.INITIAL_CAPITAL
        self.trades: List[Trade] = []
        self.equity_curve = []
        self.orderbook_history = []
        
        # Market data
        self.historical_data = pd.DataFrame()
        self.current_index = 0
        
    def fetch_historical_data(self):
        """Fetch historical data from Bybit"""
        logger.info(f"Fetching historical data for {self.config.SYMBOL}")
        
        start_timestamp = int(pd.Timestamp(self.config.START_DATE).timestamp() * 1000)
        end_timestamp = int(pd.Timestamp(self.config.END_DATE).timestamp() * 1000)
        
        self.historical_data = self.data_fetcher.fetch_klines(
            symbol=self.config.SYMBOL,
            interval=self.config.INTERVAL,
            start_time=start_timestamp,
            end_time=end_timestamp,
            category=self.config.CATEGORY
        )
        
        logger.info(f"Fetched {len(self.historical_data)} data points")
        return self.historical_data
    
    def simulate_orderbook(self, price: float, volume: float) -> Dict:
        """Simulate orderbook based on historical price and volume"""
        spread_pct = 0.0005  # 0.05% spread
        depth_levels = 20
        
        bids = []
        asks = []
        
        for i in range(depth_levels):
            bid_price = price * (1 - spread_pct * (i + 1))
            ask_price = price * (1 + spread_pct * (i + 1))
            
            # Simulate volume distribution
            level_volume = volume * np.exp(-i * 0.3) / depth_levels
            
            bids.append([str(bid_price), str(level_volume)])
            asks.append([str(ask_price), str(level_volume)])
        
        return {
            'b': bids,
            'a': asks,
            'ts': int(datetime.now().timestamp() * 1000),
            'u': self.current_index
        }
    
    def execute_order(self, side: str, price: float, size: float) -> Optional[Trade]:
        """Simulate order execution with fees and slippage"""
        if size <= 0:
            return None
        
        # Apply slippage
        if side.lower() == "buy":
            execution_price = price * (1 + self.config.SLIPPAGE)
            cost = execution_price * size
            fee = cost * self.config.MAKER_FEE
            
            if self.balance < cost + fee:
                logger.warning(f"Insufficient balance for buy order: {cost + fee:.2f} > {self.balance:.2f}")
                return None
            
            self.balance -= (cost + fee)
            self.market_maker.position += size
            
        else:  # sell
            execution_price = price * (1 - self.config.SLIPPAGE)
            proceeds = execution_price * size
            fee = proceeds * self.config.MAKER_FEE
            
            if self.market_maker.position < size:
                logger.warning(f"Insufficient position for sell order: {size:.4f} > {self.market_maker.position:.4f}")
                return None
            
            self.balance += (proceeds - fee)
            self.market_maker.position -= size
        
        # Calculate PnL for sells
        pnl = 0
        if side.lower() == "sell" and self.market_maker.avg_entry_price > 0:
            pnl = (execution_price - self.market_maker.avg_entry_price) * size - fee
        
        # Update average entry price for buys
        if side.lower() == "buy":
            if self.market_maker.position > 0:
                total_cost = self.market_maker.avg_entry_price * (self.market_maker.position - size) + execution_price * size
                self.market_maker.avg_entry_price = total_cost / self.market_maker.position
            else:
                self.market_maker.avg_entry_price = execution_price
        
        trade = Trade(
            timestamp=self.historical_data.iloc[self.current_index]['timestamp'],
            side=side,
            price=execution_price,
            quantity=size,
            fee=fee,
            pnl=pnl,
            position_after=self.market_maker.position,
            balance_after=self.balance
        )
        
        self.trades.append(trade)
        return trade
    
    def check_order_fills(self, current_price: float, current_volume: float):
        """Check if any pending orders would be filled"""
        filled_orders = []
        
        # Check buy orders
        for order_id, order in list(self.market_maker.active_orders['buy'].items()):
            if current_price <= order['price']:
                trade = self.execute_order("Buy", order['price'], order['size'])
                if trade:
                    filled_orders.append(order_id)
                    logger.debug(f"Buy order filled: {order['size']:.4f} @ {order['price']:.2f}")
        
        # Check sell orders
        for order_id, order in list(self.market_maker.active_orders['sell'].items()):
            if current_price >= order['price']:
                trade = self.execute_order("Sell", order['price'], order['size'])
                if trade:
                    filled_orders.append(order_id)
                    logger.debug(f"Sell order filled: {order['size']:.4f} @ {order['price']:.2f}")
        
        # Remove filled orders
        for order_id in filled_orders:
            if order_id in self.market_maker.active_orders['buy']:
                del self.market_maker.active_orders['buy'][order_id]
            if order_id in self.market_maker.active_orders['sell']:
                del self.market_maker.active_orders['sell'][order_id]
    
    def update_market_data(self, row):
        """Update market maker with current market data"""
        current_price = float(row['close'])
        current_volume = float(row['volume'])
        
        # Simulate orderbook
        orderbook = self.simulate_orderbook(current_price, current_volume)
        
        # Update market maker's orderbook
        self.market_maker.orderbook['bid'] = [(float(b), float(b)) for b in orderbook['b']]
        self.market_maker.orderbook['ask'] = [(float(a), float(a)) for a in orderbook['a']]
        
        if self.market_maker.orderbook['bid'] and self.market_maker.orderbook['ask']:
            best_bid = self.market_maker.orderbook['bid']
            best_ask = self.market_maker.orderbook['ask']
            self.market_maker.mid_price = (best_bid + best_ask) / 2
            self.market_maker.last_price = self.market_maker.mid_price
    
    def calculate_metrics(self) -> Dict:
        """Calculate performance metrics"""
        if not self.trades:
            return {
                'total_trades': 0,
                'total_pnl': 0,
                'win_rate': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'final_balance': self.balance,
                'return_pct': 0
            }
        
        df_trades = pd.DataFrame([asdict(t) for t in self.trades])
        
        # Calculate metrics
        total_pnl = df_trades['pnl'].sum()
        profitable_trades = df_trades[df_trades['pnl'] > 0]
        win_rate = len(profitable_trades) / len(df_trades) * 100 if len(df_trades) > 0 else 0
        
        # Calculate returns for Sharpe ratio
        if len(self.equity_curve) > 1:
            returns = pd.Series(self.equity_curve).pct_change().dropna()
            sharpe_ratio = np.sqrt(252) * returns.mean() / returns.std() if returns.std() > 0 else 0
        else:
            sharpe_ratio = 0
        
        # Calculate max drawdown
        equity_series = pd.Series(self.equity_curve)
        rolling_max = equity_series.expanding().max()
        drawdowns = (equity_series - rolling_max) / rolling_max
        max_drawdown = drawdowns.min() * 100 if len(drawdowns) > 0 else 0
        
        # Final metrics
        final_equity = self.balance + (self.market_maker.position * self.market_maker.last_price if self.market_maker.position != 0 else 0)
        return_pct = ((final_equity - self.initial_capital) / self.initial_capital) * 100
        
        return {
            'total_trades': len(df_trades),
            'total_pnl': total_pnl,
            'win_rate': win_rate,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'final_balance': self.balance,
            'final_equity': final_equity,
            'return_pct': return_pct,
            'avg_trade_pnl': total_pnl / len(df_trades) if len(df_trades) > 0 else 0,
            'total_fees': df_trades['fee'].sum()
        }
    
    async def run_backtest(self):
        """Main backtest loop"""
        logger.info("Starting backtest...")
        
        # Fetch historical data
        if self.historical_data.empty:
            self.fetch_historical_data()
        
        if self.historical_data.empty:
            logger.error("No historical data available")
            return
        
        # Main backtest loop
        for index, row in self.historical_data.iterrows():
            self.current_index = index
            
            # Update market data
            self.update_market_data(row)
            
            # Check for order fills
            self.check_order_fills(float(row['close']), float(row['volume']))
            
            # Update orders (market maker logic)
            self.market_maker.update_orders()
            
            # Calculate current equity
            current_equity = self.balance
            if self.market_maker.position != 0:
                current_equity += self.market_maker.position * float(row['close'])
            self.equity_curve.append(current_equity)
            
            # Log progress
            if index % 100 == 0:
                logger.info(f"Progress: {index}/{len(self.historical_data)} | "
                          f"Balance: ${self.balance:.2f} | "
                          f"Position: {self.market_maker.position:.4f} | "
                          f"Equity: ${current_equity:.2f}")
        
        # Calculate final metrics
        metrics = self.calculate_metrics()
        
        logger.info("=" * 50)
        logger.info("BACKTEST RESULTS")
        logger.info("=" * 50)
        for key, value in metrics.items():
            if isinstance(value, float):
                logger.info(f"{key}: {value:.2f}")
            else:
                logger.info(f"{key}: {value}")
        
        return metrics
    
    def save_results(self, filename: str = "backtest_results.csv"):
        """Save backtest results to CSV"""
        if self.trades:
            df_trades = pd.DataFrame([asdict(t) for t in self.trades])
            df_trades.to_csv(f"trades_{filename}", index=False)
            logger.info(f"Trades saved to trades_{filename}")
        
        # Save equity curve
        df_equity = pd.DataFrame({
            'timestamp': self.historical_data['timestamp'][:len(self.equity_curve)],
            'equity': self.equity_curve
        })
        df_equity.to_csv(f"equity_{filename}", index=False)
        logger.info(f"Equity curve saved to equity_{filename}")

# Main execution
async def main():
    # Import your Config class
    from config import Config
    
    # Create backtest config
    backtest_config = BacktestConfig(
        SYMBOL="BTCUSDT",
        CATEGORY="linear",
        INITIAL_CAPITAL=10000,
        START_DATE="2024-01-01",
        END_DATE="2024-01-31",
        INTERVAL="5"  # 5-minute intervals
    )
    
    # Create market maker instance (without live connection)
    market_maker = MarketMaker()
    market_maker.session = None  # Disable live trading
    
    # Create and run backtest
    backtester = BacktestEngine(market_maker, backtest_config)
    results = await backtester.run_backtest()
    
    # Save results
    backtester.save_results()
    
    return results

if __name__ == "__main__":
    asyncio.run(main())
```

## Configuration File Updates

Update your `config.py` to support backtesting mode:

```python
class Config:
    # Trading parameters
    SYMBOL = "BTCUSDT"
    CATEGORY = "linear"  # spot, linear, inverse
    TESTNET = True
    
    # API credentials (leave empty for backtesting)
    API_KEY = ""
    API_SECRET = ""
    
    # Order parameters
    MIN_ORDER_SIZE = 0.001
    MAX_ORDER_SIZE = 1.0
    ORDER_SIZE_INCREMENT = 0.001
    ORDER_LEVELS = 3
    
    # Spread parameters
    BASE_SPREAD = 0.002  # 0.2%
    MIN_SPREAD = 0.001   # 0.1%
    MAX_SPREAD = 0.01    # 1%
    
    # Position management
    MAX_POSITION = 10.0
    INVENTORY_EXTREME = 0.8  # 80% of max position
    
    # Risk management
    STOP_LOSS_PCT = 0.02    # 2%
    TAKE_PROFIT_PCT = 0.03  # 3%
    
    # Volatility parameters
    VOLATILITY_WINDOW = 20
    VOLATILITY_STD = 2
    
    # Timing
    UPDATE_INTERVAL = 5  # seconds
    RECONNECT_DELAY = 10  # seconds
```

## Key Features

### Historical Data Integration
The backtester fetches real historical kline data directly from Bybit's API, ensuring realistic market conditions. It supports multiple timeframes and can handle spot, linear, and inverse markets.

### Order Book Simulation
Since historical orderbook data requires specialized services, the backtester simulates realistic orderbook depths based on historical price and volume data. This provides a reasonable approximation for testing market making strategies.

### Performance Metrics
The system calculates comprehensive metrics including:
- **Total P&L and win rate**
- **Sharpe ratio** for risk-adjusted returns
- **Maximum drawdown** for risk assessment
- **Transaction costs** including maker/taker fees
- **Position tracking** throughout the backtest

### Trade Execution Simulation
The backtester simulates realistic trade execution with:
- **Slippage modeling** to account for market impact
- **Fee calculation** based on maker/taker rates
- **Position management** with proper average entry price tracking
- **Order fill logic** based on limit price crossing

## Running the Backtester

To run the backtester with your bot:

```python
# Example: Backtest for different time periods
async def run_multiple_backtests():
    periods = [
        ("2024-01-01", "2024-01-31"),
        ("2024-02-01", "2024-02-28"),
        ("2024-03-01", "2024-03-31")
    ]
    
    all_results = []
    for start, end in periods:
        backtest_config = BacktestConfig(
            SYMBOL="BTCUSDT",
            START_DATE=start,
            END_DATE=end,
            INTERVAL="5"
        )
        
        market_maker = MarketMaker()
        market_maker.session = None
        
        backtester = BacktestEngine(market_maker, backtest_config)
        results = await backtester.run_backtest()
        all_results.append(results)
    
    return all_results

# Run it
asyncio.run(run_multiple_backtests())
```

## Advanced Features

### Multi-Asset Backtesting
Extend the backtester to test multiple trading pairs simultaneously:

```python
async def backtest_portfolio(symbols: List[str]):
    portfolio_results = {}
    
    for symbol in symbols:
        backtest_config = BacktestConfig(
            SYMBOL=symbol,
            INITIAL_CAPITAL=10000 / len(symbols)  # Split capital
        )
        
        market_maker = MarketMaker()
        market_maker.config.SYMBOL = symbol
        market_maker.session = None
        
        backtester = BacktestEngine(market_maker, backtest_config)
        results = await backtester.run_backtest()
        portfolio_results[symbol] = results
    
    return portfolio_results
```

### Parameter Optimization
Test different parameter combinations to find optimal settings:

```python
def optimize_parameters():
    param_grid = {
        'BASE_SPREAD': [0.001, 0.002, 0.003],
        'ORDER_LEVELS': [2, 3, 4, 5],
        'MAX_POSITION': [5, 10, 15]
    }
    
    best_params = None
    best_sharpe = -float('inf')
    
    for base_spread in param_grid['BASE_SPREAD']:
        for order_levels in param_grid['ORDER_LEVELS']:
            for max_position in param_grid['MAX_POSITION']:
                # Update config
                market_maker = MarketMaker()
                market_maker.config.BASE_SPREAD = base_spread
                market_maker.config.ORDER_LEVELS = order_levels
                market_maker.config.MAX_POSITION = max_position
                market_maker.session = None
                
                # Run backtest
                backtester = BacktestEngine(market_maker, BacktestConfig())
                results = asyncio.run(backtester.run_backtest())
                
                if results['sharpe_ratio'] > best_sharpe:
                    best_sharpe = results['sharpe_ratio']
                    best_params = {
                        'BASE_SPREAD': base_spread,
                        'ORDER_LEVELS': order_levels,
                        'MAX_POSITION': max_position,
                        'sharpe_ratio': best_sharpe
                    }
    
    return best_params
```

## Visualization

Add visualization capabilities to analyze results:

```python
import matplotlib.pyplot as plt

def plot_backtest_results(backtester: BacktestEngine):
    fig, axes = plt.subplots(3, 1, figsize=(12, 10))
    
    # Equity curve
    axes.plot(backtester.equity_curve)
    axes.set_title('Equity Curve')
    axes.set_ylabel('Portfolio Value ($)')
    axes.grid(True)
    
    # Position over time
    positions = [t.position_after for t in backtester.trades]
    timestamps = [t.timestamp for t in backtester.trades]
    axes.plot(timestamps, positions)
    axes.set_title('Position Size Over Time')
    axes.set_ylabel('Position')
    axes.grid(True)
    
    # Trade P&L distribution
    pnls = [t.pnl for t in backtester.trades if t.pnl != 0]
    axes.hist(pnls, bins=30, edgecolor='black')
    axes.set_title('Trade P&L Distribution')
    axes.set_xlabel('P&L ($)')
    axes.set_ylabel('Frequency')
    axes.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('backtest_results.png')
    plt.show()
```

## Important Considerations

1. **Data Quality**: The backtester uses Bybit's historical kline data, which provides OHLCV information. For more granular tick-level data, consider specialized data providers.

2. **Orderbook Simulation**: Real orderbook data requires premium services. The simulated orderbook provides a reasonable approximation but may not capture all market microstructure effects.

3. **Latency Modeling**: In live trading, order and data latency significantly impact performance. Consider adding latency simulation for more realistic results.

4. **Transaction Costs**: Always include realistic fee structures in your backtests. Bybit's maker/taker fees can significantly impact profitability.

5. **Market Impact**: Large orders may move the market. The current implementation uses a simple slippage model, but you may want to implement more sophisticated impact models for larger positions.

This backtester provides a solid foundation for testing your market making strategy with real Bybit historical data. You can extend it further based on your specific requirements and trading style.
Awesome project. Below is a drop‑in backtesting harness that reuses your MarketMaker logic and replays “live” historical data pulled from Bybit via pybit’s unified (v5) public endpoints. It:

- Fetches klines (candles) from Bybit for your symbol and time range
- Steps through time at your chosen cadence (e.g., 1 minute)
- Lets your bot place/cancel orders exactly as written (session=None path)
- Simulates fills when price “touches” your quotes within each step
- Tracks position, average entry, realized/unrealized PnL, equity curve, drawdowns, and Sharpe
- Optionally enforces stop-loss/TP levels using your config percentages

You don’t have to modify your MarketMaker class. Save this as backtest.py next to your existing code.

Python code (backtester)

```python
# backtest.py
import math
import time
import uuid
import random
import argparse
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
from pybit.unified_trading import HTTP

# Import your bot and config
from market_maker import MarketMaker  # rename if your file is different
from config import Config

logger = logging.getLogger("Backtester")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# -------- Utilities

def to_ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


@dataclass
class BacktestParams:
    symbol: str
    category: str = "linear"            # "linear" | "inverse" | "spot"
    interval: str = "1"                 # Bybit kline interval as string: "1","3","5","15","60","240","D",...
    start: datetime = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end: datetime = datetime(2024, 1, 2, tzinfo=timezone.utc)
    testnet: bool = False
    # Execution model
    maker_fee: float = 0.0002           # 2 bps; set negative if you receive rebates (e.g., -0.00025)
    fill_on_touch: bool = True          # fill if price touches order
    volume_cap_ratio: float = 0.25      # cap fills to a fraction of candle volume (0..1)
    rng_seed: int = 42                  # for deterministic intra-candle path
    sl_tp_emulation: bool = True        # emulate SL/TP using Config STOP_LOSS_PCT / TAKE_PROFIT_PCT


class BybitHistoricalData:
    """
    Pulls historical klines via Bybit v5 public API using pybit.
    """

    def __init__(self, params: BacktestParams):
        self.params = params
        # For public endpoints, keys are optional
        self.http = HTTP(testnet=params.testnet)

    def get_klines(self) -> pd.DataFrame:
        """
        Fetch klines over [start, end) range, handling pagination (limit=1000 bars).
        Returns DataFrame sorted by start time with columns:
        ['start', 'open', 'high', 'low', 'close', 'volume', 'turnover']
        All price columns are floats; 'start' is int ms.
        """
        start_ms = to_ms(self.params.start)
        end_ms = to_ms(self.params.end)
        all_rows: List[List[str]] = []
        limit = 1000

        while True:
            resp = self.http.get_kline(
                category=self.params.category,
                symbol=self.params.symbol,
                interval=self.params.interval,
                start=start_ms,
                end=end_ms,
                limit=limit
            )
            if resp.get("retCode") != 0:
                raise RuntimeError(f"Bybit get_kline error: {resp.get('retMsg')}")

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

            # Be kind to the API
            time.sleep(0.05)

        if not all_rows:
            raise ValueError("No klines returned for the requested range.")

        df = pd.DataFrame(all_rows, columns=["start", "open", "high", "low", "close", "volume", "turnover"])
        for col in ["start"]:
            df[col] = df[col].astype(np.int64)
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            df[col] = df[col].astype(float)

        df = df.sort_values("start").reset_index(drop=True)
        return df


class FillEngine:
    """
    Simulates maker fills using intra-candle path approximation.
    """
    def __init__(self, params: BacktestParams):
        self.params = params
        random.seed(params.rng_seed)

    def _intrabar_path(self, o: float, h: float, l: float, c: float, ts_ms: int) -> List[float]:
        """
        Generate a simple deterministic intra-candle path: open -> mid-extreme -> other extreme -> close.
        The ordering (O-H-L-C) vs (O-L-H-C) is seeded by timestamp for variety but reproducibility.
        """
        rnd = (ts_ms // 60000) ^ self.params.rng_seed
        go_high_first = (rnd % 2 == 0)
        if go_high_first:
            return [o, (o + h) / 2, h, (h + l) / 2, l, (l + c) / 2, c]
        else:
            return [o, (o + l) / 2, l, (l + h) / 2, h, (h + c) / 2, c]

    def _volume_capacity(self, candle_volume: float) -> float:
        """
        Simplistic capacity: only a fraction of the candle's volume is available to our maker orders.
        Interpreting 'volume' as contract or base-asset volume depending on market; adjust as needed.
        """
        return max(0.0, candle_volume) * self.params.volume_cap_ratio

    def simulate_fills_for_step(
        self,
        mm: MarketMaker,
        krow: pd.Series
    ) -> Dict[str, float]:
        """
        Apply fills to mm.active_orders for this kline step.
        Returns dict with aggregate 'filled_buy' and 'filled_sell' notional sizes for logging/debug.
        """
        o, h, l, c = krow.open, krow.high, krow.low, krow.close
        ts_ms = int(krow.start)
        path = self._intrabar_path(o, h, l, c, ts_ms)

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
                pnl_delta, pos_delta, new_avg = self._apply_fill(mm, side="Buy", price=price, size=fill_size)
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
                pnl_delta, pos_delta, new_avg = self._apply_fill(mm, side="Sell", price=price, size=fill_size)
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

    def _apply_fill(self, mm: MarketMaker, side: str, price: float, size: float) -> Tuple[float, float, float]:
        """
        Apply a trade fill to MarketMaker state. Returns (realized_pnl_delta, position_delta, new_avg_entry).
        Fee is charged on notional.
        """
        # Fee on notional (maker)
        fee = abs(price * size) * self.params.maker_fee

        pos_before = mm.position
        avg_before = mm.avg_entry_price or 0.0

        realized_pnl_delta = 0.0
        pos_delta = size if side.lower() == "buy" else -size

        # If position direction changes or reduces, compute realized pnl for the closed portion
        if pos_before == 0 or np.sign(pos_before) == np.sign(pos_delta):
            # Adding to same-direction inventory
            new_pos = pos_before + pos_delta
            new_avg = ((abs(pos_before) * avg_before) + (abs(pos_delta) * price)) / max(abs(new_pos), 1e-12)
            mm.position = new_pos
            mm.avg_entry_price = new_avg
        else:
            # Reducing or flipping
            if abs(pos_delta) <= abs(pos_before):
                # Partial or full reduction
                closed = abs(pos_delta)
                realized_pnl_delta = self._closed_pnl(side, entry=avg_before, fill=price, qty=closed)
                new_pos = pos_before + pos_delta
                mm.position = new_pos
                mm.avg_entry_price = avg_before if new_pos != 0 else 0.0
            else:
                # Flip: close old, open new in opposite direction
                closed = abs(pos_before)
                realized_pnl_delta = self._closed_pnl(side, entry=avg_before, fill=price, qty=closed)
                leftover = abs(pos_delta) - closed
                new_side_delta = np.sign(pos_delta) * leftover
                mm.position = new_side_delta
                mm.avg_entry_price = price

        # Accrue fees into realized pnl
        mm.unrealized_pnl = (mm.last_price - mm.avg_entry_price) * mm.position if mm.position != 0 else 0.0

        # Store realized pnl in a side buffer on mm via attribute injection if not present
        if not hasattr(mm, "realized_pnl"):
            mm.realized_pnl = 0.0
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
        if not hasattr(mm, "realized_pnl"):
            mm.realized_pnl = 0.0
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
    def __init__(self, params: BacktestParams, cfg: Optional[Config] = None):
        self.params = params
        self.cfg = cfg or Config()
        self.data = BybitHistoricalData(params)
        self.fill_engine = FillEngine(params)

        # Bot under test
        self.mm = MarketMaker()
        # Force backtest mode (no session) but keep config and symbol/category consistent
        self.mm.session = None
        self.mm.config.SYMBOL = params.symbol
        self.mm.config.CATEGORY = params.category

        # Metrics
        self.equity_curve: List[Tuple[int, float]] = []   # (timestamp ms, equity)
        self.drawdowns: List[float] = []
        self.trades: List[Dict] = []  # optional detailed trade log

    def run(self) -> Dict[str, float]:
        klines = self.data.get_klines()

        # Initialize prices with first candle open
        first = klines.iloc[0]
        self.mm.last_price = first.open
        self.mm.mid_price = first.open

        # Track equity; assume starting cash (USDT) is implicit 0 and PnL purely from trading.
        # If you want to start with specific cash, add it here and include fees accordingly.
        if not hasattr(self.mm, "realized_pnl"):
            self.mm.realized_pnl = 0.0

        for idx, row in klines.iterrows():
            # 1) Let bot update/cancel/place orders based on current mid
            self.mm.update_orders()

            # 2) Simulate fills within this step
            fill_stats = self.fill_engine.simulate_fills_for_step(self.mm, row)

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
    def _max_drawdown(equity: List[float]) -> float:
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
    parser = argparse.ArgumentParser(description="Backtest MarketMaker with Bybit historical data.")
    parser.add_argument("--symbol", type=str, default="BTCUSDT")
    parser.add_argument("--category", type=str, default="linear", choices=["linear", "inverse", "spot"])
    parser.add_argument("--interval", type=str, default="1", help="Bybit kline interval: 1,3,5,15,60,240,D,...")
    parser.add_argument("--start", type=str, required=True, help="UTC start, e.g. 2024-06-01T00:00:00")
    parser.add_argument("--end", type=str, required=True, help="UTC end, e.g. 2024-06-07T00:00:00")
    parser.add_argument("--testnet", action="store_true", help="Use Bybit testnet")
    parser.add_argument("--maker_fee", type=float, default=0.0002)
    parser.add_argument("--volume_cap_ratio", type=float, default=0.25)
    parser.add_argument("--no_sl_tp", action="store_true", help="Disable SL/TP emulation")
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
        sl_tp_emulation=not args.no_sl_tp
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
```

How it works with your MarketMaker

- It keeps session=None so your place_order/cancel methods just mutate active_orders in memory. No exchange calls are made.
- Each step:
  1) The bot calls update_orders() using the current mid price (the candle’s open/close). This cancels and replaces quotes per your logic and recalculates spread based on your volatility/inventory functions.
  2) The fill engine simulates intra-candle price motion and fills orders if touched, applying maker fees and updating position/avg_entry/unrealized_pnl on the same MarketMaker instance.
  3) Equity is tracked as realized_pnl + unrealized at the candle close.

Setup and run

1) Install deps (versions shown are examples):
   - pybit >= 5.x (unified_trading)
   - pandas, numpy

   pip install "pybit==5.*" pandas numpy

2) Make sure your file layout is like:
   - config.py
   - market_maker.py (contains your MarketMaker class)
   - backtest.py

3) Example run (UTC times):
   python backtest.py --symbol BTCUSDT --category linear --interval 1 --start 2024-06-01T00:00:00 --end 2024-06-07T00:00:00

4) Outputs:
   - Summary stats
   - equity_curve.csv for plotting

Notes and knobs you can tweak

- maker_fee: Set to your actual maker fee (e.g., 0.0002 for 2 bps). Use a negative number if your tier receives a rebate.
- volume_cap_ratio: Limits total filled size per candle to a fraction of that candle’s volume; this curbs unrealistic fills in thin markets.
- fill_on_touch: True means a resting order fills if price touches; turn off if you want stricter crossing logic.
- sl_tp_emulation: If True, stop-loss and take-profit levels are enforced intra-bar using your Config’s STOP_LOSS_PCT and TAKE_PROFIT_PCT.
- Intra-candle path: A simple deterministic O-H-L-C or O-L-H-C sequence. You can replace _intrabar_path with a microstructure model or use public trades if you want tick-accurate replay.

Optional improvements

- Use Bybit public trades (tick-level) for exact touch/cross checks and partial fills by tick volume.
- Record a full trade blotter (timestamp, side, price, qty, fee) for analysis.
- Add inventory and notional risk limits; halt if exceeded.
- Annualize Sharpe using your step frequency and trading days.
- Simulate latency and queue priority (your quotes might not be first at the touch).

If you want, tell me your current Config values (spreads, order levels, sizes, limits) and the exact symbol/time window you care about, and I’ll tailor the defaults and add a quick plotter for PnL and inventory.
I'll create a comprehensive backtester for your Bybit market maker bot that uses live historical data from Bybit. This backtester will simulate the bot's trading logic using real market data to evaluate its performance.

## Complete Backtester Implementation

Here's a full backtesting framework that fetches historical data from Bybit and simulates your market maker strategy:

```python
import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from pybit.unified_trading import HTTP
from dataclasses import dataclass
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class BacktestConfig:
    """Backtesting configuration parameters"""
    # Trading parameters (inherited from original config)
    SYMBOL: str = "BTCUSDT"
    CATEGORY: str = "linear"  # spot, linear, inverse
    TESTNET: bool = True
    
    # Market making parameters
    BASE_SPREAD: float = 0.001
    MIN_SPREAD: float = 0.0005
    MAX_SPREAD: float = 0.005
    ORDER_LEVELS: int = 3
    MIN_ORDER_SIZE: float = 0.001
    MAX_ORDER_SIZE: float = 0.1
    ORDER_SIZE_INCREMENT: float = 0.001
    MAX_POSITION: float = 1.0
    INVENTORY_EXTREME: float = 0.8
    
    # Risk management
    STOP_LOSS_PCT: float = 0.02
    TAKE_PROFIT_PCT: float = 0.03
    
    # Volatility parameters
    VOLATILITY_WINDOW: int = 20
    VOLATILITY_STD: float = 2.0
    
    # Backtesting specific parameters
    INITIAL_BALANCE: float = 10000.0
    MAKER_FEE: float = -0.00025  # Negative for rebate
    TAKER_FEE: float = 0.00075
    START_DATE: str = "2024-01-01"
    END_DATE: str = "2024-01-31"
    KLINE_INTERVAL: str = "5"  # 1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M
    SLIPPAGE_PCT: float = 0.0001  # 0.01% slippage

class HistoricalDataFetcher:
    """Fetches historical data from Bybit API"""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.session = HTTP(testnet=config.TESTNET)
        
    def fetch_klines(self, start_time: datetime, end_time: datetime) -> pd.DataFrame:
        """Fetch historical kline data from Bybit"""
        all_klines = []
        current_start = int(start_time.timestamp() * 1000)
        end_timestamp = int(end_time.timestamp() * 1000)
        
        while current_start < end_timestamp:
            try:
                response = self.session.get_kline(
                    category=self.config.CATEGORY,
                    symbol=self.config.SYMBOL,
                    interval=self.config.KLINE_INTERVAL,
                    start=current_start,
                    end=min(current_start + 200 * 60 * 1000 * int(self.config.KLINE_INTERVAL), end_timestamp),
                    limit=200
                )
                
                if response['retCode'] == 0:
                    klines = response['result']['list']
                    if not klines:
                        break
                    
                    all_klines.extend(klines)
                    # Update start time for next batch
                    last_timestamp = int(klines)  # List is reverse sorted
                    current_start = last_timestamp + 1
                    
                    # Rate limiting
                    time.sleep(0.1)
                else:
                    logger.error(f"Failed to fetch klines: {response['retMsg']}")
                    break
                    
            except Exception as e:
                logger.error(f"Error fetching klines: {e}")
                break
        
        # Convert to DataFrame
        if all_klines:
            df = pd.DataFrame(all_klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
            ])
            df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                df[col] = df[col].astype(float)
            df = df.sort_values('timestamp').reset_index(drop=True)
            return df
        
        return pd.DataFrame()

    def generate_orderbook_from_ohlc(self, price: float, spread_pct: float = 0.001) -> Dict:
        """Generate synthetic orderbook from OHLC data"""
        spread = price * spread_pct
        bid_price = price - spread / 2
        ask_price = price + spread / 2
        
        # Generate multiple levels
        orderbook = {
            'bid': [(bid_price - i * spread * 0.1, 1000 * (5 - i)) for i in range(5)],
            'ask': [(ask_price + i * spread * 0.1, 1000 * (5 - i)) for i in range(5)]
        }
        return orderbook

class BacktestEngine:
    """Main backtesting engine"""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.data_fetcher = HistoricalDataFetcher(config)
        self.reset()
        
    def reset(self):
        """Reset backtesting state"""
        # Account state
        self.balance = self.config.INITIAL_BALANCE
        self.position = 0
        self.avg_entry_price = 0
        self.realized_pnl = 0
        self.unrealized_pnl = 0
        self.total_fees = 0
        
        # Order tracking
        self.active_orders = {'buy': {}, 'sell': {}}
        self.order_history = []
        self.trade_history = []
        
        # Market data
        self.orderbook = {'bid': [], 'ask': []}
        self.last_price = 0
        self.mid_price = 0
        self.spread = self.config.BASE_SPREAD
        
        # Volatility tracking
        self.price_history = []
        self.current_volatility = 1.0
        
        # Performance metrics
        self.equity_curve = []
        self.max_drawdown = 0
        self.trades_count = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
    def calculate_volatility(self) -> float:
        """Calculate current market volatility using Bollinger Bands"""
        if len(self.price_history) < self.config.VOLATILITY_WINDOW:
            return 1.0
        
        prices = pd.Series(self.price_history[-self.config.VOLATILITY_WINDOW:])
        sma = prices.rolling(window=self.config.VOLATILITY_WINDOW).mean().iloc[-1]
        std = prices.rolling(window=self.config.VOLATILITY_WINDOW).std().iloc[-1]
        
        if std == 0:
            return 1.0

        upper_band = sma + (self.config.VOLATILITY_STD * std)
        lower_band = sma - (self.config.VOLATILITY_STD * std)
        band_width = (upper_band - lower_band) / sma
        
        volatility = band_width / 0.02
        return max(0.5, min(3.0, volatility))
    
    def calculate_spread(self) -> float:
        """Calculate dynamic spread based on volatility and inventory"""
        base_spread = self.config.BASE_SPREAD
        volatility_adj = self.current_volatility
        
        inventory_ratio = abs(self.position) / self.config.MAX_POSITION if self.config.MAX_POSITION > 0 else 0
        inventory_adj = 1 + (inventory_ratio * 0.5)
        
        spread = base_spread * volatility_adj * inventory_adj
        return max(self.config.MIN_SPREAD, min(self.config.MAX_SPREAD, spread))
    
    def calculate_order_prices(self) -> Tuple[List[float], List[float]]:
        """Calculate order prices for multiple levels"""
        if not self.mid_price:
            return [], []
        
        spread = self.calculate_spread()
        bid_prices = []
        ask_prices = []
        
        for i in range(self.config.ORDER_LEVELS):
            level_spread = spread * (1 + i * 0.2)
            bid_price = self.mid_price * (1 - level_spread)
            ask_price = self.mid_price * (1 + level_spread)
            
            bid_prices.append(round(bid_price, 2))
            ask_prices.append(round(ask_price, 2))
        
        return bid_prices, ask_prices
    
    def calculate_order_sizes(self) -> Tuple[List[float], List[float]]:
        """Calculate order sizes with inventory management"""
        base_size = self.config.MIN_ORDER_SIZE
        increment = self.config.ORDER_SIZE_INCREMENT
        
        buy_sizes = []
        sell_sizes = []
        
        inventory_ratio = self.position / self.config.MAX_POSITION if self.config.MAX_POSITION > 0 else 0
        
        for i in range(self.config.ORDER_LEVELS):
            size = base_size + (i * increment)
            
            buy_size = size * (1 - max(0, inventory_ratio))
            sell_size = size * (1 + min(0, inventory_ratio))
            
            buy_sizes.append(round(buy_size, 4))
            sell_sizes.append(round(sell_size, 4))
        
        return buy_sizes, sell_sizes
    
    def check_order_fills(self, high_price: float, low_price: float, current_price: float):
        """Check if any orders would be filled"""
        filled_orders = []
        
        # Check buy orders
        for order_id, order in list(self.active_orders['buy'].items()):
            if low_price <= order['price']:
                # Order filled
                execution_price = order['price'] * (1 + self.config.SLIPPAGE_PCT)
                self.execute_trade('buy', execution_price, order['size'])
                filled_orders.append(order_id)
                
        # Check sell orders  
        for order_id, order in list(self.active_orders['sell'].items()):
            if high_price >= order['price']:
                # Order filled
                execution_price = order['price'] * (1 - self.config.SLIPPAGE_PCT)
                self.execute_trade('sell', execution_price, order['size'])
                filled_orders.append(order_id)
        
        # Remove filled orders
        for order_id in filled_orders:
            if order_id in self.active_orders['buy']:
                del self.active_orders['buy'][order_id]
            if order_id in self.active_orders['sell']:
                del self.active_orders['sell'][order_id]
    
    def execute_trade(self, side: str, price: float, size: float):
        """Execute a trade and update position"""
        trade_value = price * size
        fee = abs(trade_value * self.config.MAKER_FEE)
        
        if side == 'buy':
            # Update position
            new_position = self.position + size
            if self.position >= 0:
                # Adding to long position
                self.avg_entry_price = ((self.position * self.avg_entry_price) + 
                                       (size * price)) / new_position if new_position > 0 else 0
            else:
                # Closing short position
                if size >= abs(self.position):
                    # Position flipped to long
                    closed_size = abs(self.position)
                    pnl = closed_size * (self.avg_entry_price - price)
                    self.realized_pnl += pnl
                    
                    remaining_size = size - closed_size
                    self.avg_entry_price = price if remaining_size > 0 else 0
                else:
                    # Partially closed short
                    pnl = size * (self.avg_entry_price - price)
                    self.realized_pnl += pnl
                    
            self.position = new_position
            self.balance -= trade_value + fee
            
        else:  # sell
            # Update position
            new_position = self.position - size
            if self.position <= 0:
                # Adding to short position
                self.avg_entry_price = ((abs(self.position) * self.avg_entry_price) + 
                                       (size * price)) / abs(new_position) if new_position < 0 else 0
            else:
                # Closing long position
                if size >= self.position:
                    # Position flipped to short
                    closed_size = self.position
                    pnl = closed_size * (price - self.avg_entry_price)
                    self.realized_pnl += pnl
                    
                    remaining_size = size - closed_size
                    self.avg_entry_price = price if remaining_size > 0 else 0
                else:
                    # Partially closed long
                    pnl = size * (price - self.avg_entry_price)
                    self.realized_pnl += pnl
                    
            self.position = new_position
            self.balance += trade_value - fee
        
        self.total_fees += fee
        self.trades_count += 1
        
        # Record trade
        self.trade_history.append({
            'timestamp': self.current_time,
            'side': side,
            'price': price,
            'size': size,
            'fee': fee,
            'position': self.position,
            'balance': self.balance,
            'realized_pnl': self.realized_pnl
        })
    
    def update_orders(self):
        """Update limit orders based on current market conditions"""
        # Cancel all existing orders
        self.active_orders = {'buy': {}, 'sell': {}}
        
        # Check inventory limits
        if abs(self.position) >= self.config.MAX_POSITION * self.config.INVENTORY_EXTREME:
            return
        
        # Calculate new order prices and sizes
        bid_prices, ask_prices = self.calculate_order_prices()
        buy_sizes, sell_sizes = self.calculate_order_sizes()
        
        # Place new orders
        for i in range(self.config.ORDER_LEVELS):
            if i < len(bid_prices) and i < len(buy_sizes) and buy_sizes[i] > 0:
                order_id = str(uuid.uuid4())
                self.active_orders['buy'][order_id] = {
                    'price': bid_prices[i],
                    'size': buy_sizes[i]
                }
            
            if i < len(ask_prices) and i < len(sell_sizes) and sell_sizes[i] > 0:
                order_id = str(uuid.uuid4())
                self.active_orders['sell'][order_id] = {
                    'price': ask_prices[i],
                    'size': sell_sizes[i]
                }
    
    def run_backtest(self) -> Dict:
        """Run the backtest simulation"""
        logger.info(f"Starting backtest from {self.config.START_DATE} to {self.config.END_DATE}")
        
        # Fetch historical data
        start_dt = datetime.strptime(self.config.START_DATE, "%Y-%m-%d")
        end_dt = datetime.strptime(self.config.END_DATE, "%Y-%m-%d")
        
        logger.info("Fetching historical data from Bybit...")
        df = self.data_fetcher.fetch_klines(start_dt, end_dt)
        
        if df.empty:
            logger.error("No historical data fetched")
            return {}
        
        logger.info(f"Fetched {len(df)} candles")
        
        # Run simulation
        for idx, row in df.iterrows():
            self.current_time = row['timestamp']
            
            # Update market data
            self.orderbook = self.data_fetcher.generate_orderbook_from_ohlc(row['close'])
            self.last_price = row['close']
            self.mid_price = row['close']
            
            # Update price history
            self.price_history.append(self.last_price)
            if len(self.price_history) > 100:
                self.price_history.pop(0)
            
            # Calculate volatility
            self.current_volatility = self.calculate_volatility()
            
            # Update orders
            self.update_orders()
            
            # Check for order fills
            self.check_order_fills(row['high'], row['low'], row['close'])
            
            # Calculate unrealized PnL
            if self.position != 0:
                if self.position > 0:
                    self.unrealized_pnl = self.position * (row['close'] - self.avg_entry_price)
                else:
                    self.unrealized_pnl = abs(self.position) * (self.avg_entry_price - row['close'])
            else:
                self.unrealized_pnl = 0
            
            # Update equity curve
            equity = self.balance + self.unrealized_pnl
            self.equity_curve.append({
                'timestamp': self.current_time,
                'equity': equity,
                'balance': self.balance,
                'position': self.position,
                'unrealized_pnl': self.unrealized_pnl,
                'realized_pnl': self.realized_pnl
            })
        
        # Close final position at market price
        if self.position != 0:
            final_price = df.iloc[-1]['close']
            if self.position > 0:
                self.execute_trade('sell', final_price, abs(self.position))
            else:
                self.execute_trade('buy', final_price, abs(self.position))
        
        return self.calculate_metrics()
    
    def calculate_metrics(self) -> Dict:
        """Calculate performance metrics"""
        equity_df = pd.DataFrame(self.equity_curve)
        
        if equity_df.empty:
            return {}
        
        # Calculate returns
        equity_df['returns'] = equity_df['equity'].pct_change()
        
        # Maximum drawdown
        equity_df['cummax'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['cummax']) / equity_df['cummax']
        max_drawdown = equity_df['drawdown'].min()
        
        # Sharpe ratio (assuming 0 risk-free rate)
        sharpe_ratio = equity_df['returns'].mean() / equity_df['returns'].std() * np.sqrt(252) if equity_df['returns'].std() > 0 else 0
        
        # Win rate
        trades_df = pd.DataFrame(self.trade_history)
        if not trades_df.empty:
            trades_df['pnl'] = trades_df['realized_pnl'].diff()
            winning_trades = len(trades_df[trades_df['pnl'] > 0])
            losing_trades = len(trades_df[trades_df['pnl'] < 0])
            win_rate = winning_trades / len(trades_df) if len(trades_df) > 0 else 0
        else:
            winning_trades = 0
            losing_trades = 0
            win_rate = 0
        
        final_equity = self.balance + self.unrealized_pnl
        total_return = (final_equity - self.config.INITIAL_BALANCE) / self.config.INITIAL_BALANCE
        
        metrics = {
            'initial_balance': self.config.INITIAL_BALANCE,
            'final_balance': self.balance,
            'final_equity': final_equity,
            'total_return': total_return,
            'realized_pnl': self.realized_pnl,
            'total_fees': self.total_fees,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'total_trades': self.trades_count,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'avg_position': np.mean([e['position'] for e in self.equity_curve]),
            'max_position': max([abs(e['position']) for e in self.equity_curve])
        }
        
        return metrics
    
    def save_results(self, filename: str = 'backtest_results.csv'):
        """Save backtest results to CSV"""
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df.to_csv(f'equity_curve_{filename}', index=False)
        
        trades_df = pd.DataFrame(self.trade_history)
        if not trades_df.empty:
            trades_df.to_csv(f'trades_{filename}', index=False)
        
        logger.info(f"Results saved to equity_curve_{filename} and trades_{filename}")

async def main():
    """Main function to run the backtest"""
    config = BacktestConfig(
        SYMBOL="BTCUSDT",
        CATEGORY="linear",
        START_DATE="2024-01-01",
        END_DATE="2024-01-07",
        INITIAL_BALANCE=10000,
        KLINE_INTERVAL="5"
    )
    
    backtester = BacktestEngine(config)
    results = backtester.run_backtest()
    
    # Print results
    print("\n=== Backtest Results ===")
    for key, value in results.items():
        if isinstance(value, float):
            print(f"{key}: {value:.4f}")
        else:
            print(f"{key}: {value}")
    
    # Save results
    backtester.save_results()
    
    # Plot equity curve (optional)
    try:
        import matplotlib.pyplot as plt
        equity_df = pd.DataFrame(backtester.equity_curve)
        
        fig, axes = plt.subplots(3, 1, figsize=(12, 10))
        
        # Equity curve
        axes.plot(equity_df['timestamp'], equity_df['equity'])
        axes.set_title('Equity Curve')
        axes.set_ylabel('Equity (USDT)')
        
        # Position over time
        axes.plot(equity_df['timestamp'], equity_df['position'])
        axes.axhline(y=0, color='r', linestyle='--', alpha=0.3)
        axes.set_title('Position Over Time')
        axes.set_ylabel('Position Size')
        
        # PnL components
        axes.plot(equity_df['timestamp'], equity_df['realized_pnl'], label='Realized PnL')
        axes.plot(equity_df['timestamp'], equity_df['unrealized_pnl'], label='Unrealized PnL')
        axes.set_title('Profit and Loss')
        axes.set_ylabel('PnL (USDT)')
        axes.legend()
        
        plt.tight_layout()
        plt.savefig('backtest_charts.png')
        plt.show()
        
    except ImportError:
        logger.info("Matplotlib not installed, skipping charts")

if __name__ == "__main__":
    asyncio.run(main())
```

## Key Features of the Backtester

### **Historical Data Integration**
The backtester fetches real historical kline data directly from Bybit's API. It handles pagination automatically since Bybit limits responses to 200 candles per request. The data includes OHLCV (Open, High, Low, Close, Volume) information for accurate simulation.

### **Order Fill Simulation**
- Simulates limit order fills based on high/low prices of each candle
- Applies realistic slippage to execution prices
- Tracks maker fees (rebates) for limit orders
- Maintains order book state throughout the simulation

### **Position Management**
- Accurately tracks position size and average entry price
- Calculates realized and unrealized PnL in real-time
- Implements inventory limits and risk management rules
- Simulates the same order sizing logic as the live bot

### **Performance Metrics**
The backtester calculates comprehensive metrics including:
- Total return and final equity
- Maximum drawdown
- Sharpe ratio
- Win rate and trade statistics
- Fee impact analysis
- Position utilization metrics

## Configuration Guide

Create a `config.py` file with your parameters:

```python
class Config:
    # Market parameters
    SYMBOL = "BTCUSDT"
    CATEGORY = "linear"  # For perpetual futures
    TESTNET = True  # Use testnet for safety
    
    # Market making parameters
    BASE_SPREAD = 0.001  # 0.1% base spread
    MIN_SPREAD = 0.0005
    MAX_SPREAD = 0.005
    ORDER_LEVELS = 3
    MIN_ORDER_SIZE = 0.001
    MAX_ORDER_SIZE = 0.1
    ORDER_SIZE_INCREMENT = 0.001
    MAX_POSITION = 1.0
    
    # Risk parameters
    STOP_LOSS_PCT = 0.02
    TAKE_PROFIT_PCT = 0.03
    INVENTORY_EXTREME = 0.8
    
    # Volatility parameters
    VOLATILITY_WINDOW = 20
    VOLATILITY_STD = 2.0
    
    # Backtesting parameters
    INITIAL_BALANCE = 10000
    START_DATE = "2024-01-01"
    END_DATE = "2024-01-31"
    KLINE_INTERVAL = "5"  # 5-minute candles
```

## Running the Backtest

1. **Install dependencies:**
```bash
pip install pybit pandas numpy matplotlib
```

2. **Run the backtester:**
```python
python backtest.py
```

3. **Analyze results:**
The backtester will output:
- Performance metrics to console
- `equity_curve_backtest_results.csv` - Detailed equity progression
- `trades_backtest_results.csv` - Individual trade records
- `backtest_charts.png` - Visualization of results

## Advanced Features

### **Multi-timeframe Analysis**
You can modify the `KLINE_INTERVAL` to test different timeframes. Bybit supports intervals from 1 minute to monthly data.

### **Walk-forward Optimization**
Split your data into training and testing periods to avoid overfitting:

```python
# Train on first 80% of data
train_end = start_dt + (end_dt - start_dt) * 0.8
backtester_train = BacktestEngine(config)
train_results = backtester_train.run_backtest()

# Test on remaining 20%
config.START_DATE = train_end.strftime("%Y-%m-%d")
backtester_test = BacktestEngine(config)
test_results = backtester_test.run_backtest()
```

### **Parameter Optimization**
You can wrap the backtest in an optimization loop to find optimal parameters:

```python
import itertools

param_grid = {
    'BASE_SPREAD': [0.0005, 0.001, 0.002],
    'ORDER_LEVELS': [2, 3, 4],
    'VOLATILITY_WINDOW': [10, 20, 30]
}

best_sharpe = -float('inf')
best_params = {}

for params in itertools.product(*param_grid.values()):
    config_dict = dict(zip(param_grid.keys(), params))
    config = BacktestConfig(**config_dict)
    
    backtester = BacktestEngine(config)
    results = backtester.run_backtest()
    
    if results['sharpe_ratio'] > best_sharpe:
        best_sharpe = results['sharpe_ratio']
        best_params = config_dict
```

## Important Considerations

- **Data Quality**: The backtester uses real historical data from Bybit, ensuring realistic results
- **Execution Assumptions**: The simulation assumes limit orders get filled when price crosses the order level
- **Market Impact**: The backtester doesn't model market impact from large orders
- **Latency**: Network latency isn't simulated but can be added via execution delays

This backtester provides a robust framework for evaluating your market maker strategy using actual Bybit historical data, giving you confidence before deploying with real capital.
