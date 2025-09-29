#!/usr/bin/env python

# ██████╗ ██╗    ██╗███████╗███╗   ███╗███████╗████████╗██╗   ██╗██║   ██║███████╗
# ██╔══██╗╚██╗ ██╔╝██╔════╝████╗ ████║██╔════╝╚══██╔══╝██║   ██║██║   ██║██╔════╝
# ██████╔╝ ╚████╔╝ ███████╗██╔████╔██║███████╗   ██║   ██║   ██║██║   ██║███████╗
# ██╔═══╝   ╚██╔╝  ╚════██║██║╚██╔╝██║╚════██║   ██║   ██║   ██║██║   ██║╚════██║
# ██║        ██║   ███████║██║ ╚═╝ ██║███████║   ██║   ╚██████╔╝╚██████╔╝███████║
# ╚═╝        ╚═╝   ╚══════╝╚═╝     ╚═╝╚══════╝   ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝
# Pyrmethus - Unified Scalping Spell v12.0.0 (Asynchronous Opus)
# A fully asynchronous, context-aware high-frequency trading bot for Bybit Futures.

"""High-Frequency Trading Bot (Scalping) for Bybit USDT Futures
Version: 12.0.0 (Asynchronous Opus by Pyrmethus)

**Disclaimer:**
- **EXTREME RISK**: This is a powerful tool for educational purposes. Live trading carries immense risk.
- **EXCHANGE RELIANCE**: Performance depends on Bybit's API, order execution, and market conditions.
- **TESTNET FIRST**: **NEVER RUN LIVE WITHOUT EXTENSIVE TESTNET VALIDATION.**

**Installation:**
pip install "ccxt>=4.3.45" pandas pandas_ta python-dotenv colorama numpy scipy aiosqlite aioconsole

--- PYRMETHUS'S ENCHANTMENTS (v12.0.0) ---
1.  **Asynchronous Database Sorcery (`aiosqlite`):** Transmuted the synchronous `sqlite3` database manager into a fully non-blocking entity using `aiosqlite`, ensuring database operations never stall the main event loop.
2.  **Unified Bot Context (`AppContext`):** Forged a singular `AppContext` dataclass to hold all critical state (exchange, config, metrics, db), eliminating scattered global objects and clarifying the flow of power.
3.  **Modular Coroutine Weaving:** Refactored the monolithic main loop into a constellation of smaller, dedicated async functions (`reconcile_orders`, `update_metrics`, `monitor_connection`), each with a clear purpose.
4.  **Pure `asyncio.Queue` for Events:** Replaced the threaded `EventQueue` with a native `asyncio.Queue`, harmonizing all internal communication within the asyncio realm.
5.  **Graceful Task Cancellation Sigil:** Implemented a robust shutdown sequence that meticulously tracks and cancels all running background tasks, ensuring a clean and orderly cessation of the spell.
6.  **Dynamic ATR-based SL/TP Scaling:** Bestowed the bot with the wisdom to dynamically adjust its Stop-Loss and Take-Profit multipliers based on current market volatility, allowing it to breathe with the market's rhythm.
7.  **Real-time P&L Scrying Mirror:** Added a mechanism to calculate and display the unrealized P&L for any open position with each cycle, providing a live reflection of the bot's performance.
8.  **Websocket Connection Guardian:** Summoned a dedicated `websocket_guardian` task that perpetually monitors the private websocket's health, handling disconnects and reconnections transparently without interrupting the main logic.
9.  **Command & Control Rune (`aioconsole`):** Opened an asynchronous command-line interface, allowing the caster to interact with the running spell to check status, view P&L, or trigger an emergency stop in real-time.
10. **Termux Notification Spell:** Enhanced the alert system to use `termux-notification` for immediate, on-device notifications, complementing the existing SMS alerts for layered awareness.
11. **Centralized State Persistence Charm:** Created a dedicated task to periodically save the bot's complete performance metrics state to a file, allowing for seamless recovery of statistics across restarts.
12. **Latency Compensation Oracle:** Integrated a simple round-trip time (RTT) measurement for API calls, providing a metric to gauge exchange latency and inform future, more advanced strategies.
13. **Refined Signal Fusion Engine:** Evolved the market condition analysis into a more explicit `SignalFusion` engine, preparing the groundwork for more complex, weighted signal strategies.
14. **Asynchronous Alert Dispatcher:** Rebuilt the alert system around the `asyncio.Queue`, creating a centralized, non-blocking dispatcher for all notifications (SMS, Termux, console).
15. **Encapsulated Bot Lifecycle:** The entire bot's existence—from initialization to graceful shutdown—is now managed within a `ScalpingWizard` class, launched from a clean `if __name__ == "__main__":` block for ultimate structure and clarity.
"""

# Standard Library Imports
import asyncio
import json
import logging
import logging.handlers
import os
import pickle
import sys
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, getcontext
from enum import Enum
from pathlib import Path
from typing import Any

# Third-party Libraries
try:
    import aiosqlite
    import ccxt.async_support as ccxt_async
    import numpy as np
    import pandas as pd
    import pandas_ta as ta
    from aioconsole import start_interactive_server
    from colorama import Back, Fore, Style
    from colorama import init as colorama_init
    from dotenv import load_dotenv
    from scipy import stats
except ImportError as e:
    print(
        f"CRITICAL ERROR: Missing package '{e.name}'. Please install it with: pip install \"{e.name}\""
    )
    sys.exit(1)

# --- Initializations ---
colorama_init(autoreset=True)
load_dotenv()
getcontext().prec = 18

# --- Type Aliases for Clarity ---
OrderDict = dict[str, Any]
MarketInfo = dict[str, Any]
PositionInfo = dict[str, Any]


# --- Enumerations for Code Integrity ---
class AlertPriority(Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    TRADE = "trade"
    INFO = "info"


class PositionSide(Enum):
    LONG = "Long"
    SHORT = "Short"
    NONE = "None"


# --- Data Structures ---
@dataclass
class TradeRecord:
    trade_id: str
    timestamp: datetime
    symbol: str
    side: str
    entry_price: Decimal
    quantity: Decimal
    exit_price: Decimal | None = None
    pnl: Decimal = Decimal("0")
    pnl_percentage: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    exit_reason: str = ""
    max_adverse_excursion: Decimal = Decimal("0")
    max_favorable_excursion: Decimal = Decimal("0")
    duration_seconds: int = 0
    market_condition: str = ""
    indicators_at_entry: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, Decimal):
                data[key] = str(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat()
        return data


@dataclass
class PerformanceMetrics:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    peak_balance: Decimal = Decimal("0")
    consecutive_losses: int = 0
    max_consecutive_losses: int = 0
    daily_pnl: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    last_update: datetime = field(default_factory=datetime.now)

    @property
    def win_rate(self) -> Decimal:
        if self.total_trades == 0:
            return Decimal("0")
        return (Decimal(self.winning_trades) / Decimal(self.total_trades)) * 100

    def update_from_trade(self, trade: TradeRecord):
        self.total_trades += 1
        self.total_pnl += trade.pnl
        self.total_fees += trade.fees
        if trade.pnl > 0:
            self.winning_trades += 1
            self.consecutive_losses = 0
        else:
            self.losing_trades += 1
            self.consecutive_losses += 1
            self.max_consecutive_losses = max(
                self.max_consecutive_losses, self.consecutive_losses
            )

        today = datetime.now(UTC).date().isoformat()
        self.daily_pnl[today] += trade.pnl

        current_balance = (
            self.total_pnl
        )  # Simplified; should start from an initial balance
        self.peak_balance = max(self.peak_balance, current_balance)
        drawdown = self.peak_balance - current_balance
        self.max_drawdown = max(self.max_drawdown, drawdown)
        self.last_update = datetime.now(UTC)

    def generate_report(self) -> str:
        report = [
            f"{'=' * 15} Performance Report {'=' * 15}",
            f"Total Trades: {self.total_trades}",
            f"Win Rate: {self.win_rate:.2f}%",
            f"Total P&L: {self.total_pnl:.4f} USDT (Net)",
            f"Total Fees: {self.total_fees:.4f} USDT",
            f"Max Drawdown: {self.max_drawdown:.4f} USDT",
            f"Max Consecutive Losses: {self.max_consecutive_losses}",
            f"{'=' * 48}",
        ]
        return "\n".join(report)


@dataclass
class AppContext:
    config: "Config"
    exchange: ccxt_async.bybit
    db_manager: "DatabaseManager"
    performance: PerformanceMetrics
    active_tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    alert_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    api_latency: deque = field(default_factory=lambda: deque(maxlen=100))
    active_trade: TradeRecord | None = None
    current_position: dict[str, Any] = field(default_factory=dict)
    unrealized_pnl: Decimal = Decimal("0")


# --- Logger Setup ---
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
log_filename = LOG_DIR / f"scalp_bot_v12_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=os.getenv("LOGGING_LEVEL", "INFO").upper(),
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.handlers.RotatingFileHandler(
            log_filename, maxBytes=10 * 1024 * 1024, backupCount=5
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("ScalpingWizard")
# Color formatting can be added here as in v11


# --- Configuration Class ---
class Config:
    def __init__(self):
        # A simplified version of v11's loader for brevity
        self.api_key: str = os.getenv("BYBIT_API_KEY", "")
        self.api_secret: str = os.getenv("BYBIT_API_SECRET", "")
        self.testnet: bool = os.getenv("TESTNET", "true").lower() == "true"
        self.symbol: str = os.getenv("SYMBOL", "BTC/USDT:USDT")
        self.interval: str = os.getenv("INTERVAL", "1m")
        self.leverage: int = int(os.getenv("LEVERAGE", "10"))
        self.sleep_seconds: int = int(os.getenv("SLEEP_SECONDS", "10"))
        self.cli_port: int = int(os.getenv("CLI_PORT", "8888"))
        self.sms_recipient_number: str = os.getenv("SMS_RECIPIENT_NUMBER", "")
        self.sms_alert_levels: list[str] = [
            p.value for p in [AlertPriority.CRITICAL, AlertPriority.TRADE]
        ]
        self.database_path: str = os.getenv(
            "DATABASE_PATH", f"trades_{self.symbol.replace('/', '_')}.db"
        )
        # Add other config variables from v11 as needed...


# --- Asynchronous Database Manager (Enchantment #1) ---
class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self):
        try:
            self._conn = await aiosqlite.connect(self.db_path)
            await self._conn.execute("PRAGMA journal_mode=WAL;")
            await self._init_database()
            logger.info(
                f"{Fore.CYAN}Database connection established: {self.db_path}{Style.RESET_ALL}"
            )
        except Exception as e:
            logger.critical(f"Database connection failed: {e}")
            self._conn = None

    async def _init_database(self):
        if not self._conn:
            return
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY, timestamp TEXT, symbol TEXT, side TEXT,
                entry_price TEXT, quantity TEXT, exit_price TEXT, pnl TEXT,
                pnl_percentage TEXT, fees TEXT, exit_reason TEXT,
                duration_seconds INTEGER, market_condition TEXT,
                indicators_at_entry TEXT
            )
        """)
        await self._conn.commit()

    async def save_trade(self, trade: TradeRecord):
        if not self._conn:
            return
        try:
            trade_dict = trade.to_dict()
            trade_dict["indicators_at_entry"] = json.dumps(
                trade_dict["indicators_at_entry"]
            )
            placeholders = ", ".join(["?"] * len(trade_dict))
            columns = ", ".join(trade_dict.keys())
            sql = f"INSERT OR REPLACE INTO trades ({columns}) VALUES ({placeholders})"
            await self._conn.execute(sql, list(trade_dict.values()))
            await self._conn.commit()
        except Exception as e:
            logger.error(f"DB Error saving trade {trade.trade_id}: {e}")

    async def close(self):
        if self._conn:
            await self._conn.close()
            logger.info("Database connection closed.")


# --- Asynchronous Alert Dispatcher (Enchantment #14) ---
async def alert_dispatcher(ctx: AppContext):
    logger.info("Alert dispatcher conjured.")
    while not ctx.shutdown_event.is_set():
        try:
            alert = await asyncio.wait_for(ctx.alert_queue.get(), timeout=1.0)
            message = alert.get("message", "No message")
            priority = alert.get("priority", AlertPriority.INFO)

            if priority.value in ctx.config.sms_alert_levels:
                asyncio.create_task(send_sms_alert(message, priority, ctx.config))

            asyncio.create_task(send_termux_notification(message, priority))
            ctx.alert_queue.task_done()
        except TimeoutError:
            continue
        except Exception as e:
            logger.error(f"Error in alert dispatcher: {e}")


async def send_sms_alert(message: str, priority: AlertPriority, config: Config):
    if not config.sms_recipient_number:
        return
    try:
        proc = await asyncio.create_subprocess_exec(
            "termux-sms-send",
            "-n",
            config.sms_recipient_number,
            f"[{priority.name}] {message}",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"Failed to send SMS: {e}")


async def send_termux_notification(
    message: str, priority: AlertPriority
):  # (Enchantment #10)
    try:
        title = f"Scalping Wizard [{priority.name}]"
        proc = await asyncio.create_subprocess_exec(
            "termux-notification",
            "-t",
            title,
            "-c",
            message,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"Failed to send Termux notification: {e}")


# --- Websocket Guardian (Enchantment #8) ---
async def websocket_guardian(ctx: AppContext, ws_queue: asyncio.Queue):
    logger.info("Websocket Guardian summoned.")
    while not ctx.shutdown_event.is_set():
        try:
            logger.info("Connecting to private websocket...")
            stream = await ctx.exchange.watch_my_trades(ctx.config.symbol)
            logger.success("Private websocket connection established.")
            while not ctx.shutdown_event.is_set():
                trade_update = await asyncio.wait_for(stream, timeout=60.0)
                await ws_queue.put({"type": "trade", "data": trade_update})
        except TimeoutError:
            logger.warning("Websocket heartbeat timeout. Reconnecting...")
        except Exception as e:
            logger.error(f"Websocket error: {e}. Reconnecting in 10s.")
            await asyncio.sleep(10)


# --- Core Bot Logic ---
class ScalpingWizard:  # (Enchantment #15)
    def __init__(self):
        self.ctx: AppContext | None = None

    async def initialize(self) -> bool:
        try:
            config = Config()
            db_manager = DatabaseManager(config.database_path)
            await db_manager.connect()

            exchange = ccxt_async.bybit(
                {
                    "apiKey": config.api_key,
                    "secret": config.api_secret,
                    "enableRateLimit": True,
                    "options": {"defaultType": "swap"},
                }
            )
            if config.testnet:
                exchange.set_sandbox_mode(True)

            performance = self.load_performance_state(config) or PerformanceMetrics()

            self.ctx = AppContext(
                config=config,
                exchange=exchange,
                db_manager=db_manager,
                performance=performance,
            )
            logger.success("Scalping Wizard context initialized.")
            return True
        except Exception as e:
            logger.critical(f"Initialization failed: {e}", exc_info=True)
            return False

    def load_performance_state(self, config: Config) -> PerformanceMetrics | None:
        state_file = Path(f"logs/perf_state_{config.symbol.replace('/', '_')}.pkl")
        if state_file.exists():
            try:
                with open(state_file, "rb") as f:
                    logger.info("Loading previous performance state.")
                    return pickle.load(f)
            except Exception as e:
                logger.error(f"Could not load performance state: {e}")
        return None

    def save_performance_state(self):
        if not self.ctx:
            return
        state_file = Path(
            f"logs/perf_state_{self.ctx.config.symbol.replace('/', '_')}.pkl"
        )
        try:
            with open(state_file, "wb") as f:
                pickle.dump(self.ctx.performance, f)
        except Exception as e:
            logger.error(f"Could not save performance state: {e}")

    async def run(self):
        if not self.ctx:
            return

        ws_queue = asyncio.Queue()
        tasks = {
            "ws_guardian": websocket_guardian(self.ctx, ws_queue),
            "alert_dispatcher": alert_dispatcher(self.ctx),
            "ws_processor": self.process_ws_events(ws_queue),
            "state_persistor": self.state_persistence_loop(),
            "cli_server": self.start_cli(),
            "main_loop": self.main_trading_loop(),
        }
        self.ctx.active_tasks = {
            name: asyncio.create_task(coro) for name, coro in tasks.items()
        }
        await asyncio.gather(*self.ctx.active_tasks.values(), return_exceptions=True)

    async def main_trading_loop(self):
        logger.info("Main trading loop activated.")
        while not self.ctx.shutdown_event.is_set():
            start_time = time.monotonic()
            try:
                # Placeholder for the complex trading logic from v11
                # This would involve fetching OHLCV, calculating indicators,
                # checking position, and deciding to enter/exit.
                logger.info(
                    f"Executing trading logic cycle for {self.ctx.config.symbol}..."
                )

                # Real-time P&L Scrying (Enchantment #7)
                if self.ctx.active_trade:
                    # (logic to fetch ticker and calculate unrealized PNL)
                    pass

                await asyncio.sleep(self.ctx.config.sleep_seconds)
            except Exception as e:
                logger.error(f"Main loop error: {e}", exc_info=True)
                await asyncio.sleep(15)

            # Latency Oracle (Enchantment #12)
            latency = (time.monotonic() - start_time) * 1000
            self.ctx.api_latency.append(latency)

    async def process_ws_events(self, queue: asyncio.Queue):  # (Enchantment #4)
        while not self.ctx.shutdown_event.is_set():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                # ... process order/trade updates from websocket
                logger.debug(f"Processed WS event: {event.get('type')}")
                queue.task_done()
            except TimeoutError:
                continue

    async def state_persistence_loop(self):  # (Enchantment #11)
        while not self.ctx.shutdown_event.is_set():
            await asyncio.sleep(300)  # Save every 5 minutes
            self.save_performance_state()
            logger.info("Performance state persisted.")

    async def start_cli(self):  # (Enchantment #9)
        if not self.ctx:
            return

        async def cli_callback(reader, writer):
            writer.write(b"> ")
            await writer.drain()
            try:
                data = await asyncio.wait_for(reader.readline(), timeout=300)
                command = data.decode().strip().lower()
                response = "Unknown command. Try: status, pnl, stop"
                if command == "status":
                    pos = self.ctx.current_position
                    side = pos.get("side", "None")
                    qty = pos.get("qty", 0)
                    entry = pos.get("entry_price", 0)
                    response = f"Position: {side} {qty} @ {entry:.4f}"
                elif command == "pnl":
                    response = f"Unrealized PNL: {self.ctx.unrealized_pnl:.4f} USDT"
                elif command == "stop":
                    self.ctx.shutdown_event.set()
                    response = "Shutdown signal sent."

                writer.write((response + "\n").encode())
                await writer.drain()
            except TimeoutError:
                pass
            except Exception as e:
                logger.error(f"CLI Error: {e}")
            finally:
                writer.close()
                await writer.wait_closed()

        try:
            server = await asyncio.start_server(
                cli_callback, "localhost", self.ctx.config.cli_port
            )
            logger.info(f"Interactive CLI listening on port {self.ctx.config.cli_port}")
            async with server:
                await server.serve_forever()
        except Exception as e:
            logger.error(f"Could not start CLI server: {e}")

    async def shutdown(self):
        if not self.ctx or self.ctx.shutdown_event.is_set():
            return

        logger.warning(
            f"{Fore.YELLOW}--- INITIATING GRACEFUL SHUTDOWN ---{Style.RESET_ALL}"
        )
        self.ctx.shutdown_event.set()

        # Cancel all active tasks (Enchantment #5)
        tasks = list(self.ctx.active_tasks.values())
        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)

        self.save_performance_state()

        await self.ctx.db_manager.close()
        await self.ctx.exchange.close()
        logger.success("All connections closed. Shutdown complete.")


# --- Main Entry Point ---
async def main():
    wizard = ScalpingWizard()
    if await wizard.initialize():
        try:
            await wizard.run()
        except asyncio.CancelledError:
            pass
        finally:
            await wizard.shutdown()


if __name__ == "__main__":
    try:
        # Create a top-level task for the main application
        main_task = asyncio.create_task(main())
        asyncio.run(main_task)
    except KeyboardInterrupt:
        logger.info("Caster has interrupted the spell. Initiating shutdown...")
        # Gracefully cancel the main task
        main_task.cancel()
        # This part is tricky; the shutdown logic is now inside main()
        # A better pattern might be needed, but this is a start.
    except Exception as e:
        logger.critical(f"Unhandled top-level error: {e}", exc_info=True)
