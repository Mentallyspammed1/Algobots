import asyncio
import logging
import signal
import sys
import time
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal
from typing import Any

import pandas as pd
import pandas_ta as ta
from pybit.unified_trading import HTTP, WebSocket
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# --- 1. Setup & Configuration ---

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler("titan_public.log")],
)
logger = logging.getLogger("TitanBot")
# Mute library noise
logging.getLogger("pybit").setLevel(logging.ERROR)

@dataclass
class Config:
    """Configuration - No API Keys Required"""
    symbol: str = "BTCUSDT"
    interval: str = "5"  # 5m candles

    # Paper Trading Config
    initial_balance: float = 10000.00
    risk_per_trade: float = 0.02
    leverage: int = 10
    taker_fee: float = 0.0006  # 0.06%
    slippage_bps: float = 0.0005 # 0.05% simulated slippage

    # Strategy
    wss_threshold: float = 2.0

    # System
    ws_public_url: str = "wss://stream.bybit.com/v5/public/linear"

# --- 2. Data Structures ---

@dataclass
class InstrumentInfo:
    tick_size: Decimal
    qty_step: Decimal
    min_qty: Decimal

@dataclass
class OrderBook:
    bids: list[list[float]] = field(default_factory=list) # [price, size]
    asks: list[list[float]] = field(default_factory=list)
    timestamp: int = 0

@dataclass
class Position:
    symbol: str
    side: str
    size: float
    entry_price: float
    sl: float
    tp: float

@dataclass
class Signal:
    action: str
    score: float
    stop_loss: float
    take_profit: float
    reason: str

# --- 3. Core Components ---

class PublicDataClient:
    """Fetches Data from Bybit Public API (No Auth)"""
    def __init__(self, config: Config):
        self.cfg = config
        # testnet=False connects to Mainnet Public API
        self.http = HTTP(testnet=False)

    async def get_instrument_info(self) -> InstrumentInfo:
        """Get precision rules for the symbol"""
        try:
            resp = await asyncio.to_thread(
                self.http.get_instruments_info,
                category="linear",
                symbol=self.cfg.symbol,
            )
            info = resp["result"]["list"][0]
            return InstrumentInfo(
                tick_size=Decimal(info["priceFilter"]["tickSize"]),
                qty_step=Decimal(info["lotSizeFilter"]["qtyStep"]),
                min_qty=Decimal(info["lotSizeFilter"]["minOrderQty"]),
            )
        except Exception as e:
            logger.error(f"Init Error: {e}")
            sys.exit(1)

    async def fetch_candles(self, limit: int = 200) -> pd.DataFrame:
        """Get historical klines"""
        try:
            resp = await asyncio.to_thread(
                self.http.get_kline,
                category="linear",
                symbol=self.cfg.symbol,
                interval=self.cfg.interval,
                limit=limit,
            )
            if "result" not in resp: return pd.DataFrame()

            # [startTime, open, high, low, close, volume, turnover]
            df = pd.DataFrame(resp["result"]["list"],
                            columns=["startTime", "open", "high", "low", "close", "volume", "turnover"])
            df = df.iloc[::-1].reset_index(drop=True) # Reverse
            return df.astype(float)
        except Exception as e:
            logger.error(f"Candle Fetch Error: {e}")
            return pd.DataFrame()

class PaperExecutionEngine:
    """Internal Ledger for Simulated Trading"""
    def __init__(self, config: Config, instrument: InstrumentInfo):
        self.cfg = config
        self.ins = instrument
        self.balance = config.initial_balance
        self.position: Position | None = None
        self.trades_history = []

        # Metrics
        self.realized_pnl = 0.0
        self.daily_pnl = 0.0

    def _calculate_max_qty(self, price: float) -> float:
        """Calculate max size based on balance and leverage"""
        max_notional = self.balance * self.cfg.leverage
        qty = max_notional / price
        # Round down to step
        d_qty = Decimal(str(qty)).quantize(self.ins.qty_step, rounding=ROUND_DOWN)
        return float(d_qty)

    def _calculate_risk_qty(self, entry: float, sl: float) -> float:
        """Calculate size based on risk % distance to SL"""
        risk_amt = self.balance * self.cfg.risk_per_trade
        diff = abs(entry - sl)
        if diff == 0: return 0.0

        qty = risk_amt / diff

        # Cap at max leverage
        max_qty = self._calculate_max_qty(entry)
        return min(qty, max_qty)

    def execute_open(self, signal: Signal, market_price: float):
        if self.position: return

        qty = self._calculate_risk_qty(market_price, signal.stop_loss)
        if qty < float(self.ins.min_qty): return

        # Simulate Fees & Slippage
        slippage = market_price * self.cfg.slippage_bps
        fill_price = market_price + slippage if signal.action == "BUY" else market_price - slippage

        cost = fill_price * qty
        fee = cost * self.cfg.taker_fee

        self.balance -= fee
        self.daily_pnl -= fee

        self.position = Position(
            symbol=self.cfg.symbol,
            side="Buy" if signal.action == "BUY" else "Sell",
            size=qty,
            entry_price=fill_price,
            sl=signal.stop_loss,
            tp=signal.take_profit,
        )

        self.log_trade(f"OPEN {signal.action}", fill_price, qty, fee)

    def execute_close(self, price: float, reason: str):
        if not self.position: return

        pos = self.position

        # PnL Calc (Linear Contract)
        if pos.side == "Buy":
            pnl = (price - pos.entry_price) * pos.size
        else:
            pnl = (pos.entry_price - price) * pos.size

        fee = (price * pos.size) * self.cfg.taker_fee
        net_pnl = pnl - fee

        self.balance += net_pnl
        self.realized_pnl += net_pnl
        self.daily_pnl += net_pnl

        self.log_trade(f"CLOSE ({reason})", price, pos.size, fee, net_pnl)
        self.position = None

    def update(self, current_price: float):
        """Check Stops"""
        if not self.position: return

        p = self.position
        if p.side == "Buy":
            if current_price <= p.sl: self.execute_close(p.sl, "Stop Loss")
            elif current_price >= p.tp: self.execute_close(p.tp, "Take Profit")
        elif current_price >= p.sl: self.execute_close(p.sl, "Stop Loss")
        elif current_price <= p.tp: self.execute_close(p.tp, "Take Profit")

    def get_unrealized_pnl(self, current_price: float) -> float:
        if not self.position: return 0.0
        p = self.position
        if p.side == "Buy":
            return (current_price - p.entry_price) * p.size
        return (p.entry_price - current_price) * p.size

    def log_trade(self, type, price, qty, fee, pnl=0.0):
        logger.info(f"{type} | Px: {price:.2f} | Qty: {qty} | Fee: {fee:.4f} | PnL: {pnl:.4f}")
        self.trades_history.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "type": type,
            "price": price,
            "qty": qty,
            "pnl": pnl,
        })

# --- 4. Strategy Logic ---

class TechnicalAnalysis:
    @staticmethod
    def analyze(df: pd.DataFrame) -> dict[str, Any]:
        if df.empty: return {}

        # 1. Heikin Ashi
        ha = ta.ha(df["open"], df["high"], df["low"], df["close"])
        df["ha_close"] = ha["HA_close"]
        df["ha_open"] = ha["HA_open"]

        # 2. ZLSMA (Approximated via EMA lag reduction)
        df["zlsma"] = ta.zlma(df["close"], length=50)

        # 3. Volatility & Momentum
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)
        df["rsi"] = ta.rsi(df["close"], length=14)

        # 4. Bollinger Squeeze
        bb = ta.bbands(df["close"], length=20, std=2.0)
        kc = ta.kc(df["high"], df["low"], df["close"], length=20, scalar=1.5)

        # Last row
        c = df.iloc[-1]

        # Squeeze logic
        try:
            squeeze = bb["BBU_20_2.0"].iloc[-1] < kc["KCU_20_1.5"].iloc[-1]
        except:
            squeeze = False

        return {
            "price": c["close"],
            "ha_close": c["ha_close"],
            "ha_open": c["ha_open"],
            "zlsma": c["zlsma"],
            "atr": c["atr"],
            "rsi": c["rsi"],
            "squeeze": squeeze,
        }

class StrategyEngine:
    @staticmethod
    def decide(ta_data: dict, config: Config) -> Signal:
        score = 0.0

        # Trend
        ha_bullish = ta_data["ha_close"] > ta_data["ha_open"]
        price_bullish = ta_data["price"] > ta_data["zlsma"]

        if ha_bullish and price_bullish: score += 2.0
        elif not ha_bullish and not price_bullish: score -= 2.0

        # Momentum
        if ta_data["rsi"] > 55: score += 0.5
        elif ta_data["rsi"] < 45: score -= 0.5

        # Volatility Bonus
        if ta_data["squeeze"]: score *= 1.2

        action = "HOLD"
        if score >= config.wss_threshold: action = "BUY"
        elif score <= -config.wss_threshold: action = "SELL"

        # Dynamic Risk Levels based on ATR
        atr = ta_data["atr"]
        sl_mult = 2.0
        tp_mult = 3.0

        if action == "BUY":
            sl = ta_data["price"] - (atr * sl_mult)
            tp = ta_data["price"] + (atr * tp_mult)
        else:
            sl = ta_data["price"] + (atr * sl_mult)
            tp = ta_data["price"] - (atr * tp_mult)

        return Signal(action, score, sl, tp, f"WSS: {score:.2f}")

# --- 5. Orchestrator ---

class TitanBot:
    def __init__(self):
        self.config = Config()
        self.api = PublicDataClient(self.config)
        self.ws = WebSocket(testnet=False, channel_type="linear") # Public Mainnet

        self.state = {
            "price": 0.0,
            "book_price": 0.0, # Weighted Mid Price
            "spread": 0.0,
            "wss": 0.0,
            "signal": "INIT",
        }
        self.orderbook = OrderBook()
        self.running = True
        self.execution = None # Initialized in setup

    async def setup(self):
        logger.info("Initializing Titan Bot (Public Paper Mode)...")
        instrument_info = await self.api.get_instrument_info()
        self.execution = PaperExecutionEngine(self.config, instrument_info)
        logger.info(f"Instrument Loaded. Tick: {instrument_info.tick_size}")

    def _handle_orderbook(self, message):
        """Process L2 Orderbook Stream"""
        if "type" not in message: return

        data = message["data"]
        # On snapshot, replace. On delta, ideally update, but for simplicity in paper mode
        # we just grab the top levels provided in the push for price simulation.

        bids = data["b"]
        asks = data["a"]

        if not bids or not asks: return

        # Calculate Weighted Mid Price from Top of Book
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        bid_qty = float(bids[0][1])
        ask_qty = float(asks[0][1])

        # Micro-structure price (Volume Weighted)
        w_mid = ((best_bid * ask_qty) + (best_ask * bid_qty)) / (bid_qty + ask_qty)

        self.state["book_price"] = w_mid
        self.state["spread"] = best_ask - best_bid
        self.state["price"] = w_mid # Use OB price for strategy as it's more responsive

        # Pass price to execution engine to trigger SL/TP checks immediately
        if self.execution:
            self.execution.update(w_mid)

    async def market_stream_loop(self):
        # Subscribe to Orderbook (L2) and Tickers
        self.ws.orderbook_stream(
            depth=50,
            symbol=self.config.symbol,
            callback=self._handle_orderbook,
        )

        while self.running:
            await asyncio.sleep(1)

    async def strategy_loop(self):
        """Candle processing loop"""
        while self.running:
            try:
                if self.state["price"] == 0:
                    await asyncio.sleep(1)
                    continue

                # 1. Fetch History
                df = await self.api.fetch_candles()

                # 2. Analyze
                # Run in thread to prevent blocking WS heartbeat
                ta_data = await asyncio.to_thread(TechnicalAnalysis.analyze, df)

                # Overwrite closing price with real-time OB price for freshness
                ta_data["price"] = self.state["price"]

                # 3. Signal
                signal = Strategy.decide(ta_data, self.config)

                self.state.update({
                    "wss": signal.score,
                    "signal": signal.action,
                })

                # 4. Execute
                pos = self.execution.position

                if signal.action != "HOLD":
                    if pos:
                        # Reversal Logic
                        if (pos.side == "Buy" and signal.action == "SELL") or \
                           (pos.side == "Sell" and signal.action == "BUY"):
                            self.execution.execute_close(self.state["price"], "Reversal")

                    elif not pos:
                        # Entry Logic
                        self.execution.execute_open(signal, self.state["price"])

            except Exception as e:
                logger.error(f"Strategy Loop Error: {e}")

            await asyncio.sleep(5) # 5s logic tick

    def ui_loop(self):
        """Rich UI Dashboard"""
        layout = Layout()
        layout.split(
            Layout(name="header", size=3),
            Layout(name="upper", size=10),
            Layout(name="lower", ratio=1),
        )

        console = Console()

        with Live(layout, refresh_per_second=4, screen=True) as live:
            while self.running:
                ex = self.execution
                if not ex:
                    time.sleep(1)
                    continue

                # --- Header ---
                header = Text(f"TITAN BOT (PUBLIC PAPER) | {self.config.symbol} | L2 Feed Active", style="bold white on blue", justify="center")
                layout["header"].update(header)

                # --- Stats ---
                u_pnl = ex.get_unrealized_pnl(self.state["price"])
                total_bal = ex.balance + u_pnl

                grid = Table.grid(expand=True)
                grid.add_column(ratio=1)
                grid.add_column(ratio=1)

                # Left: Market
                mkt_table = Table(title="Market Data", style="cyan")
                mkt_table.add_column("Metric"); mkt_table.add_column("Value", justify="right")
                mkt_table.add_row("OB Price", f"{self.state['price']:.2f}")
                mkt_table.add_row("Spread", f"{self.state['spread']:.2f}")
                mkt_table.add_row("Signal", self.state["signal"], style="green" if self.state["signal"]=="BUY" else "red" if self.state["signal"]=="SELL" else "white")
                mkt_table.add_row("WSS Score", f"{self.state['wss']:.2f}")

                # Right: Account
                acc_table = Table(title="Paper Account", style="magenta")
                acc_table.add_column("Metric"); acc_table.add_column("Value", justify="right")
                acc_table.add_row("Balance", f"${ex.balance:.2f}")
                acc_table.add_row("Equity", f"${total_bal:.2f}")
                acc_table.add_row("Daily PnL", f"${ex.daily_pnl:.2f}", style="green" if ex.daily_pnl>=0 else "red")
                acc_table.add_row("Unrealized", f"${u_pnl:.2f}", style="green" if u_pnl>=0 else "red")

                grid.add_row(Panel(mkt_table), Panel(acc_table))
                layout["upper"].update(grid)

                # --- Active Position & History ---
                pos_text = Text("NO ACTIVE POSITION", style="dim white", justify="center")
                if ex.position:
                    p = ex.position
                    pos_text = Text(f"{p.side} {p.size} @ {p.entry_price:.2f} | TP: {p.tp:.2f} | SL: {p.sl:.2f}", style="bold yellow", justify="center")

                hist_table = Table(title="Trade History", expand=True)
                hist_table.add_column("Time"); hist_table.add_column("Type"); hist_table.add_column("PnL")
                for t in ex.trades_history[-5:]: # Last 5
                    hist_table.add_row(t["time"], t["type"], f"{t['pnl']:.2f}", style="green" if t["pnl"]>=0 else "red")

                layout["lower"].update(Panel(Align.center(pos_text, vertical="middle"), title="Active Position"))
                if ex.trades_history:
                    layout["lower"].update(Panel(hist_table))

                time.sleep(0.25)

    async def main(self):
        await self.setup()
        await asyncio.gather(
            self.market_stream_loop(),
            self.strategy_loop(),
            asyncio.to_thread(self.ui_loop),
        )

if __name__ == "__main__":
    bot = TitanBot()

    def cleanup(signum, frame):
        bot.running = False
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)

    try:
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        pass
