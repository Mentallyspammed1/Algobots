import asyncio
import logging
import os
import pickle
import sys
import time
from collections import deque
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from typing import Any

import aiofiles
import aiosqlite
import numpy as np
import requests
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

getcontext().prec = 28
load_dotenv()


class APIAuthError(Exception):
    pass


class WebSocketConnectionError(Exception):
    pass


class MarketInfoError(Exception):
    pass


class InitialBalanceError(Exception):
    pass


class ConfigurationError(Exception):
    pass


class OrderPlacementError(Exception):
    pass


class BybitAPIError(Exception):
    def __init__(self, message: str, ret_code: int = -1, ret_msg: str = "Unknown"):
        super().__init__(message)
        self.ret_code = ret_code
        self.ret_msg = ret_msg


class BybitRateLimitError(BybitAPIError):
    pass


class BybitInsufficientBalanceError(BybitAPIError):
    pass


from config_definitions import (
    Config,
    MarketInfo,
    TradeMetrics,
    TradingState,
    setup_logger,
)
from strategy_backtester import MarketMakingStrategy


class StateManager:
    def __init__(self, file_path: str, logger: logging.Logger):
        self.file_path = file_path
        self.logger = logger

    async def save_state(self, state: dict):
        try:
            async with aiofiles.open(self.file_path, "wb") as f:
                await f.write(pickle.dumps(state))
            self.logger.info("Bot state saved successfully.")
        except Exception as e:
            self.logger.error(f"Error saving state: {e}")

    async def load_state(self) -> dict | None:
        if not os.path.exists(self.file_path):
            return None
        try:
            async with aiofiles.open(self.file_path, "rb") as f:
                return pickle.loads(await f.read())
        except Exception as e:
            self.logger.error(
                f"Error loading state from {self.file_path}: {e}. Starting fresh.",
                exc_info=True,
            )
            return None


class DBManager:
    def __init__(self, db_file: str, logger: logging.Logger):
        self.db_file = db_file
        self.conn: aiosqlite.Connection | None = None
        self.logger = logger

    async def connect(self):
        try:
            db_uri = f"file:{self.db_file}?mode=rwc"
            self.conn = await aiosqlite.connect(db_uri, uri=True)
            await self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.row_factory = aiosqlite.Row
            self.logger.info(f"Connected to database: {self.db_file} with URI mode and WAL journal mode.")
        except Exception as e:
            self.logger.critical(f"Failed to connect to database: {e}", exc_info=True)
            sys.exit(1)

    async def close(self):
        if self.conn:
            await self.conn.close()
            self.logger.info("Database connection closed.")

    async def create_tables(self):
        if not self.conn:
            await self.connect()

        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS order_events (id INTEGER PRIMARY KEY, timestamp TEXT, order_id TEXT, order_link_id TEXT, symbol TEXT, side TEXT, order_type TEXT, price TEXT, qty TEXT, status TEXT, message TEXT, cum_exec_qty TEXT);
            CREATE TABLE IF NOT EXISTS trade_fills (id INTEGER PRIMARY KEY, timestamp TEXT, order_id TEXT, trade_id TEXT, symbol TEXT, side TEXT, exec_price TEXT, exec_qty TEXT, fee TEXT, fee_currency TEXT, pnl TEXT, realized_pnl_impact TEXT, liquidity_role TEXT);
            CREATE TABLE IF NOT EXISTS balance_updates (id INTEGER PRIMARY KEY, timestamp TEXT, currency TEXT, wallet_balance TEXT, available_balance TEXT);
            CREATE TABLE IF NOT EXISTS bot_metrics (id INTEGER PRIMARY KEY, timestamp TEXT, total_trades INTEGER, net_realized_pnl TEXT, realized_pnl TEXT, unrealized_pnl TEXT, gross_profit TEXT, gross_loss TEXT, total_fees TEXT, wins INTEGER, losses INTEGER, win_rate REAL, current_asset_holdings TEXT, average_entry_price TEXT, daily_pnl TEXT, daily_loss_pct REAL);
        """
        )

        async def _add_column_if_not_exists(
            table: str, column: str, type: str, default: str
        ):
            cursor = await self.conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in await cursor.fetchall()]
            if column not in columns:
                self.logger.warning(
                    f"Adding '{column}' column to '{table}' table for existing database."
                )
                await self.conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {type} DEFAULT {default}"
                )
                await self.conn.commit()

        await _add_column_if_not_exists("order_events", "cum_exec_qty", "TEXT", "'0'")
        await _add_column_if_not_exists(
            "trade_fills", "liquidity_role", "TEXT", "'UNKNOWN'"
        )
        await _add_column_if_not_exists("trade_fills", "realized_pnl_impact", "TEXT", "'0'")
        await _add_column_if_not_exists("bot_metrics", "realized_pnl", "TEXT", "'0'")
        await _add_column_if_not_exists(
            "bot_metrics", "net_realized_pnl", "TEXT", "'0'"
        )
        await _add_column_if_not_exists("bot_metrics", "unrealized_pnl", "TEXT", "'0'")
        await _add_column_if_not_exists("bot_metrics", "gross_profit", "TEXT", "'0'")
        await _add_column_if_not_exists("bot_metrics", "gross_loss", "TEXT", "'0'")
        await _add_column_if_not_exists("bot_metrics", "total_fees", "TEXT", "'0'")
        await _add_column_if_not_exists("bot_metrics", "wins", "INTEGER", "0")
        await _add_column_if_not_exists("bot_metrics", "losses", "INTEGER", "0")
        await _add_column_if_not_exists("bot_metrics", "win_rate", "REAL", "0.0")
        await _add_column_if_not_exists(
            "bot_metrics", "current_asset_holdings", "TEXT", "'0'"
        )
        await _add_column_if_not_exists(
            "bot_metrics", "average_entry_price", "TEXT", "'0'"
        )
        await _add_column_if_not_exists("bot_metrics", "daily_pnl", "TEXT", "'0'")
        await _add_column_if_not_exists("bot_metrics", "daily_loss_pct", "REAL", "0.0")

        await self.conn.commit()
        self.logger.info("Database tables checked/created and migrated.")

    async def log_order_event(self, order_data: dict, message: str | None = None):
        if not self.conn:
            return
        try:
            await self.conn.execute(
                "INSERT INTO order_events (timestamp, order_id, order_link_id, symbol, side, order_type, price, qty, status, message, cum_exec_qty) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    order_data.get("orderId"),
                    order_data.get("orderLinkId"),
                    order_data.get("symbol"),
                    order_data.get("side"),
                    order_data.get("orderType"),
                    str(order_data.get("price", "0")),
                    str(order_data.get("qty", "0")),
                    order_data.get("orderStatus"),
                    message,
                    str(order_data.get("cumExecQty", "0")),
                ),
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging order event to DB: {e}", exc_info=True)

    async def log_trade_fill(self, trade_data: dict, realized_pnl_impact: Decimal):
        if not self.conn:
            return
        try:
            await self.conn.execute(
                "INSERT INTO trade_fills (timestamp, order_id, trade_id, symbol, side, exec_price, exec_qty, fee, fee_currency, pnl, realized_pnl_impact, liquidity_role) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    trade_data.get("orderId"),
                    trade_data.get("execId"),
                    trade_data.get("symbol"),
                    trade_data.get("side"),
                    str(trade_data.get("execPrice", "0")),
                    str(trade_data.get("execQty", "0")),
                    str(trade_data.get("execFee", "0")),
                    trade_data.get("feeCurrency"),
                    str(trade_data.get("pnl", "0")),
                    str(realized_pnl_impact),
                    trade_data.get("execType", "UNKNOWN"),
                ),
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging trade fill to DB: {e}", exc_info=True)

    async def log_balance_update(
        self,
        currency: str,
        wallet_balance: Decimal,
        available_balance: Decimal | None = None,
    ):
        if not self.conn:
            return
        try:
            await self.conn.execute(
                "INSERT INTO balance_updates (timestamp, currency, wallet_balance, available_balance) VALUES (?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    currency,
                    str(wallet_balance),
                    str(available_balance) if available_balance else None,
                ),
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging balance update to DB: {e}", exc_info=True)

    async def log_bot_metrics(
        self,
        metrics: TradeMetrics,
        unrealized_pnl: Decimal,
        daily_pnl: Decimal,
        daily_loss_pct: float,
    ):
        if not self.conn:
            return
        try:
            await self.conn.execute(
                "INSERT INTO bot_metrics (timestamp, total_trades, net_realized_pnl, realized_pnl, unrealized_pnl, gross_profit, gross_loss, total_fees, wins, losses, win_rate, current_asset_holdings, average_entry_price, daily_pnl, daily_loss_pct) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    metrics.total_trades,
                    str(metrics.net_realized_pnl),
                    str(metrics.realized_pnl),
                    str(unrealized_pnl),
                    str(metrics.gross_profit),
                    str(metrics.gross_loss),
                    str(metrics.total_fees),
                    metrics.wins,
                    metrics.losses,
                    metrics.win_rate,
                    str(metrics.current_asset_holdings),
                    str(metrics.average_entry_price),
                    str(daily_pnl),
                    daily_loss_pct,
                ),
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging bot metrics to DB: {e}", exc_info=True)


class TradingClient:
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.http_session = HTTP(
            testnet=self.config.testnet,
            api_key=self.config.api_key,
            api_secret=self.config.api_secret,
            timeout=self.config.system.api_timeout_sec,
        )
        self.ws_public: WebSocket | None = None
        self.ws_private: WebSocket | None = None
        self.last_cancel_time = 0.0

        self._original_methods = {
            "get_instruments_info": self.get_instruments_info_impl,
            "get_wallet_balance": self.get_wallet_balance_impl,
            "get_position_info": self.get_position_info_impl,
            "set_leverage": self.set_leverage_impl,
            "get_open_orders": self.get_open_orders_impl,
            "place_order": self.place_order_impl,
            "cancel_order": self.cancel_order_impl,
            "cancel_all_orders": self.cancel_all_orders_impl,
        }
        self._initialize_api_retry_decorator()

    def _is_retryable_bybit_error(self, exception: Exception) -> bool:
        if not isinstance(exception, BybitAPIError):
            return False
        if isinstance(
            exception,
            (
                APIAuthError,
                ValueError,
                BybitRateLimitError,
                BybitInsufficientBalanceError,
            ),
        ) or isinstance(exception, (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError)):
            return False
        return True

    def _get_api_retry_decorator(self):
        return retry(
            stop=stop_after_attempt(self.config.system.api_retry_attempts),
            wait=wait_exponential_jitter(
                initial=self.config.system.api_retry_initial_delay_sec,
                max=self.config.system.api_retry_max_delay_sec,
            ),
            retry=retry_if_exception(self._is_retryable_bybit_error),
            before_sleep=before_sleep_log(self.logger, logging.WARNING, exc_info=False),
            reraise=True,
        )

    def _initialize_api_retry_decorator(self):
        api_retry = self._get_api_retry_decorator()
        for name, method in self._original_methods.items():
            setattr(self, name, api_retry(method))
        self.logger.debug("API retry decorators initialized and applied.")

    async def _run_sync_api_call(self, api_method: Callable, *args, **kwargs) -> Any:
        return await asyncio.to_thread(api_method, *args, **kwargs)

    async def _handle_response_async(self, coro: Coroutine[Any, Any, Any], action: str):
        response = await coro

        if not isinstance(response, dict):
            self.logger.error(
                f"API {action} failed: Invalid response format. Response: {response}"
            )
            raise BybitAPIError(
                f"Invalid API response for {action}",
                ret_code=-1,
                ret_msg="Invalid format",
            )

        ret_code = response.get("retCode", -1)
        ret_msg = response.get("retMsg", "Unknown error")

        if ret_code == 0:
            self.logger.debug(f"API {action} successful.")
            return response.get("result", {})

        if ret_code == 10004:
            raise APIAuthError(
                f"Authentication failed: {ret_msg}. Check API key permissions and validity."
            )
        elif ret_code in [10006, 10007, 10016, 120004, 120005]:
            raise BybitRateLimitError(
                f"API rate limit hit for {action}: {ret_msg}",
                ret_code=ret_code,
                ret_msg=ret_msg,
            )
        elif ret_code in [10001, 110001, 110003, 12130, 12131]:
            raise BybitInsufficientBalanceError(
                f"Insufficient balance for {action}: {ret_msg}",
                ret_code=ret_code,
                ret_msg=ret_msg,
            )
        elif ret_code == 10002:
            raise ValueError(
                f"API {action} parameter error: {ret_msg} (ErrCode: {ret_code})"
            )

        raise BybitAPIError(
            f"API {action} failed: {ret_msg}", ret_code=ret_code, ret_msg=ret_msg
        )

    async def get_instruments_info_impl(self) -> dict | None:
        response_coro = self._run_sync_api_call(
            self.http_session.get_instruments_info,
            category=self.config.category,
            symbol=self.config.symbol,
        )
        result = await self._handle_response_async(
            response_coro, "get_instruments_info"
        )
        return result.get("list", [{}])[0] if result else None

    async def get_wallet_balance_impl(self) -> dict | None:
        account_type = (
            "UNIFIED" if self.config.category in ["linear", "inverse"] else "SPOT"
        )
        response_coro = self._run_sync_api_call(
            self.http_session.get_wallet_balance, accountType=account_type
        )
        result = await self._handle_response_async(response_coro, "get_wallet_balance")
        return result.get("list", [{}])[0] if result else None

    async def get_position_info_impl(self) -> dict | None:
        if self.config.category not in ["linear", "inverse"]:
            return None
        response_coro = self._run_sync_api_call(
            self.http_session.get_positions,
            category=self.config.category,
            symbol=self.config.symbol,
        )
        result = await self._handle_response_async(response_coro, "get_position_info")
        if result and result.get("list"):
            for position in result["list"]:
                if position["symbol"] == self.config.symbol:
                    return position
        return None

    async def set_leverage_impl(self, leverage: Decimal) -> bool:
        if self.config.category not in ["linear", "inverse"]:
            return True
        response_coro = self._run_sync_api_call(
            self.http_session.set_leverage,
            category=self.config.category,
            symbol=self.config.symbol,
            buyLeverage=str(leverage),
            sellLeverage=str(leverage),
        )
        return (
            await self._handle_response_async(
                response_coro, f"set_leverage to {leverage}"
            )
            is not None
        )

    async def get_open_orders_impl(self) -> list[dict]:
        response_coro = self._run_sync_api_call(
            self.http_session.get_open_orders,
            category=self.config.category,
            symbol=self.config.symbol,
            limit=50,
        )
        result = await self._handle_response_async(response_coro, "get_open_orders")
        return result.get("list", []) if result else []

    async def place_order_impl(self, params: dict) -> dict | None:
        response_coro = self._run_sync_api_call(self.http_session.place_order, **params)
        return await self._handle_response_async(
            response_coro,
            f"place_order ({params.get('side')} {params.get('qty')} @ {params.get('price')})",
        )

    async def cancel_order_impl(
        self, order_id: str, order_link_id: str | None = None
    ) -> bool:
        current_time = time.time()
        if (
            current_time - self.last_cancel_time
        ) < self.config.system.cancellation_rate_limit_sec:
            await asyncio.sleep(
                self.config.system.cancellation_rate_limit_sec
                - (current_time - self.last_cancel_time)
            )

        params = {
            "category": self.config.category,
            "symbol": self.config.symbol,
            "orderId": order_id,
        }
        if order_link_id:
            params["orderLinkId"] = order_link_id
        response_coro = self._run_sync_api_call(
            self.http_session.cancel_order, **params
        )
        self.last_cancel_time = time.time()
        return (
            await self._handle_response_async(response_coro, f"cancel_order {order_id}")
            is not None
        )

    async def cancel_all_orders_impl(self) -> bool:
        params = {"category": self.config.category, "symbol": self.config.symbol}
        response_coro = self._run_sync_api_call(
            self.http_session.cancel_all_orders, **params
        )
        return (
            await self._handle_response_async(response_coro, "cancel_all_orders")
            is not None
        )

    get_instruments_info: Callable[[], Coroutine[Any, Any, dict | None]]
    get_wallet_balance: Callable[[], Coroutine[Any, Any, dict | None]]
    get_position_info: Callable[[], Coroutine[Any, Any, dict | None]]
    set_leverage: Callable[[Decimal], Coroutine[Any, Any, bool]]
    get_open_orders: Callable[[], Coroutine[Any, Any, list[dict]]]
    place_order: Callable[[dict], Coroutine[Any, Any, dict | None]]
    cancel_order: Callable[[str, str | None], Coroutine[Any, Any, bool]]
    cancel_all_orders: Callable[[], Coroutine[Any, Any, bool]]

    def _init_public_ws(self, callback: Callable):
        self.logger.info("Initializing PUBLIC orderbook stream...")
        self.ws_public = WebSocket(
            testnet=self.config.testnet, channel_type=self.config.category
        )
        self.ws_public.orderbook_stream(
            symbol=self.config.symbol, depth=1, callback=callback
        )

    def _init_private_ws(
        self, order_callback: Callable, position_callback: Callable | None = None
    ):
        self.logger.info("Initializing PRIVATE streams (orders, positions)...")
        self.ws_private = WebSocket(
            testnet=self.config.testnet,
            api_key=self.config.api_key,
            api_secret=self.config.api_secret,
            channel_type="private",
        )
        self.ws_private.order_stream(callback=order_callback)
        if position_callback and self.config.category in ["linear", "inverse"]:
            self.ws_private.position_stream(callback=position_callback)

    def close_websockets(self):
        self.logger.info("Closing WebSocket connections...")
        if self.ws_public:
            self.ws_public.exit()
            self.ws_public = None
        if self.ws_private:
            self.ws_private.exit()
            self.ws_private = None


class BybitMarketMaker:
    def __init__(self, config: Config):
        self.config = config
        self.logger = setup_logger(config.files)
        self.state_manager = StateManager(config.files.state_file, self.logger)
        self.db_manager = DBManager(config.files.db_file, self.logger)
        self.trading_client = TradingClient(self.config, self.logger)

        self.state = TradingState(
            ws_reconnect_attempts_left=self.config.system.ws_reconnect_attempts,
            price_candlestick_history=deque(
                maxlen=self.config.strategy.dynamic_spread.volatility_window_sec + 1
            ),
            circuit_breaker_price_points=deque(
                maxlen=self.config.strategy.circuit_breaker.check_window_sec * 2
            ),
        )

        self.market_info: MarketInfo | None = None
        self.is_running = False

        self.orderbook_queue: asyncio.Queue = asyncio.Queue()
        self.private_ws_queue: asyncio.Queue = asyncio.Queue()

        self.market_data_lock = asyncio.Lock()
        self.active_orders_lock = asyncio.Lock()
        self.balance_position_lock = asyncio.Lock()

        self.loop: asyncio.AbstractEventLoop | None = None

        self.logger.info(
            f"Market Maker Bot Initialized. Trading Mode: {self.config.trading_mode}"
        )
        if self.config.testnet:
            self.logger.info("Running on Bybit Testnet.")

    async def run(self):
        self.is_running = True
        self.loop = asyncio.get_running_loop()
        try:
            await self._initialize_bot()
            if self.config.trading_mode not in ["DRY_RUN", "SIMULATION"]:
                await self._connect_websockets()

            while self.is_running:
                await self._main_loop_tick()
                await asyncio.sleep(self.config.system.loop_interval_sec)

        except (
            APIAuthError,
            WebSocketConnectionError,
            asyncio.CancelledError,
            KeyboardInterrupt,
            BybitAPIError,
        ) as e:
            self.logger.info(
                f"Bot stopping gracefully due to: {type(e).__name__} - {e}"
            )
        except Exception as e:
            self.logger.critical(
                f"An unhandled critical error occurred in the main loop: {e}",
                exc_info=True,
            )
        finally:
            await self.stop()

    async def _initialize_bot(self):
        self.logger.info("Performing initial setup...")

        await self.db_manager.connect()
        await self.db_manager.create_tables()

        if not await self._fetch_market_info():
            raise MarketInfoError("Failed to fetch market info. Shutting down.")

        # Instantiate MarketMakingStrategy here
        self.strategy = MarketMakingStrategy(self.config, self.market_info)

        if not await self._update_balance_and_position():
            raise InitialBalanceError(
                "Failed to fetch initial balance/position. Shutting down."
            )

        if self.state.daily_initial_capital == Decimal("0") or (
            self.state.daily_pnl_reset_date is not None
            and self.state.daily_pnl_reset_date.date()
            < datetime.now(timezone.utc).date()
        ):
            self.state.daily_initial_capital = self.state.current_balance
            self.state.daily_pnl_reset_date = datetime.now(timezone.utc)
            self.logger.info(
                f"Daily initial capital set to: {self.state.daily_initial_capital} {self.config.quote_currency}"
            )

        if self.config.trading_mode not in ["DRY_RUN", "SIMULATION"]:
            if self.config.category in [
                "linear",
                "inverse",
            ] and not await self.trading_client.set_leverage(self.config.leverage):
                raise InitialBalanceError("Failed to set leverage. Shutting down.")
        else:
            self.logger.info(
                f"{self.config.trading_mode} mode: Skipping leverage setting."
            )

        await self._load_bot_state()

        if self.config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            if self.state.mid_price == Decimal("0"):
                mock_price = Decimal("0.1")
                self.state.mid_price = mock_price
                self.state.smoothed_mid_price = mock_price
                self.state.price_candlestick_history.append(
                    (time.time(), mock_price, mock_price, mock_price)
                )
                self.logger.info(
                    f"{self.config.trading_mode} mode: Initialized mock mid_price to {mock_price}."
                )
        await self._reconcile_orders_on_startup()
        self.logger.info("Initial setup successful.")

    async def _load_bot_state(self):
        state_data = await self.state_manager.load_state()
        if state_data:
            loaded_orders = state_data.get("active_orders", {})
            for order_id, order_data in loaded_orders.items():
                if "cumExecQty" not in order_data:
                    order_data["cumExecQty"] = Decimal("0")
                for key in ["price", "qty", "cumExecQty"]:
                    if key in order_data and isinstance(order_data[key], str):
                        try:
                            order_data[key] = Decimal(order_data[key])
                        except Exception:
                            self.logger.warning(
                                f"Could not convert {key}={order_data[key]} to Decimal for order {order_id}"
                            )

            async with self.active_orders_lock:
                self.state.active_orders = loaded_orders

            loaded_metrics_dict = state_data.get("metrics", {})
            if loaded_metrics_dict:
                metrics = TradeMetrics()
                for attr, value in loaded_metrics_dict.items():
                    if attr in [
                        "gross_profit",
                        "gross_loss",
                        "total_fees",
                        "realized_pnl",
                        "current_asset_holdings",
                        "average_entry_price",
                    ] and isinstance(value, str):
                        setattr(metrics, attr, Decimal(value))
                    elif attr == "last_pnl_update_timestamp":
                        if isinstance(value, str):
                            try:
                                setattr(metrics, attr, datetime.fromisoformat(value))
                            except ValueError:
                                setattr(metrics, attr, None)
                        else:
                            setattr(metrics, attr, value)
                    else:
                        setattr(metrics, attr, value)
                self.state.metrics = metrics
            else:
                self.state.metrics = state_data.get("metrics", self.state.metrics)

            self.state.metrics.last_pnl_update_timestamp = state_data.get(
                "metrics_last_pnl_update_timestamp"
            )

            self.state.is_paused = state_data.get("is_paused", False)
            self.state.pause_end_time = state_data.get("pause_end_time", 0.0)
            self.state.circuit_breaker_cooldown_end_time = state_data.get(
                "circuit_breaker_cooldown_end_time", 0.0
            )
            self.state.daily_initial_capital = Decimal(
                str(state_data.get("daily_initial_capital", "0"))
            )
            if isinstance(state_data.get("daily_pnl_reset_date"), str):
                self.state.daily_pnl_reset_date = datetime.fromisoformat(
                    state_data["daily_pnl_reset_date"]
                )
            else:
                self.state.daily_pnl_reset_date = state_data.get("daily_pnl_reset_date")

            async with self.market_data_lock:
                self.state.mid_price = Decimal(str(state_data.get("mid_price", "0")))
                self.state.smoothed_mid_price = Decimal(
                    str(state_data.get("smoothed_mid_price", "0"))
                )
                self.state.price_candlestick_history.extend(
                    [
                        (t, Decimal(str(h)), Decimal(str(l)), Decimal(str(c)))
                        for t, h, l, c in state_data.get(
                            "price_candlestick_history", []
                        )
                    ]
                )
                self.state.circuit_breaker_price_points.extend(
                    [
                        (t, Decimal(str(p)))
                        for t, p in state_data.get("circuit_breaker_price_points", [])
                    ]
                )

            self.logger.info(
                f"Loaded state with {len(self.state.active_orders)} active orders and metrics: {self.state.metrics}"
            )
        else:
            self.logger.info("No saved state found. Starting fresh.")

    async def _connect_websockets(self):
        self.logger.info("Connecting WebSockets...")
        try:
            self.trading_client._init_public_ws(
                lambda msg: self._schedule_coro(self.orderbook_queue.put(msg))
            )
            self.trading_client._init_private_ws(
                lambda msg: self._schedule_coro(self.private_ws_queue.put(msg)),
                lambda msg: self._schedule_coro(self.private_ws_queue.put(msg)),
            )
            self.state.ws_reconnect_attempts_left = (
                self.config.system.ws_reconnect_attempts
            )
            self.logger.info("WebSockets connected and subscribed. Queues active.")
        except Exception as e:
            self.logger.error(
                f"Failed to establish initial WebSocket connections: {e}", exc_info=True
            )
            raise WebSocketConnectionError(f"Initial WS connection failed: {e}")

    async def _reconnect_websockets(self):
        if self.state.ws_reconnect_attempts_left <= 0:
            self.logger.critical(
                "Max WebSocket reconnection attempts reached. Shutting down."
            )
            self.is_running = False
            return

        self.state.ws_reconnect_attempts_left -= 1
        delay = self.config.system.ws_reconnect_initial_delay_sec * (
            2
            ** (
                self.config.system.ws_reconnect_attempts
                - self.state.ws_reconnect_attempts_left
                - 1
            )
        )
        delay = min(delay, self.config.system.ws_reconnect_max_delay_sec)
        self.logger.warning(
            f"Attempting WebSocket reconnection in {delay:.1f} seconds... ({self.state.ws_reconnect_attempts_left} attempts left)"
        )
        await asyncio.sleep(delay)

        self.trading_client.close_websockets()
        try:
            await self._connect_websockets()
            self.logger.info("WebSocket reconnected successfully.")
        except WebSocketConnectionError:
            self.logger.error("WebSocket reconnection attempt failed.")

    async def _main_loop_tick(self):
        current_time = time.time()

        await self._process_ws_queues()

        if self.config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            await self._simulate_dry_run_price_movement(current_time)
            await self._simulate_dry_run_fills()
        else:
            await self._websocket_health_check(current_time)
            if not self.is_running:
                return

        await self._periodic_health_check(current_time)

        if await self._check_daily_loss_circuit_breaker():
            self.logger.critical("Daily loss circuit breaker tripped. Shutting down.")
            self.is_running = False
            return

        if self.state.is_paused and current_time < self.state.pause_end_time:
            self.logger.debug(
                f"Bot is paused due to circuit breaker. Resuming in {int(self.state.pause_end_time - current_time)}s."
            )
            return
        elif self.state.is_paused:
            self.logger.info("Circuit breaker pause finished. Resuming trading.")
            self.state.is_paused = False
            self.state.circuit_breaker_cooldown_end_time = (
                current_time
                + self.config.strategy.circuit_breaker.cool_down_after_trip_sec
            )

        if current_time < self.state.circuit_breaker_cooldown_end_time:
            self.logger.debug(
                f"Circuit breaker in cooldown. Resuming trading in {int(self.state.circuit_breaker_cooldown_end_time - current_time)}s."
            )
            return

        await self._manage_orders()

        if (
            current_time - self.state.last_status_report_time
            > self.config.system.status_report_interval_sec
        ):
            await self._log_status_summary()
            self.state.last_status_report_time = current_time

    async def _process_ws_queues(self):
        while True:
            try:
                message = self.orderbook_queue.get_nowait()
                await self._process_orderbook_message(message)
            except asyncio.QueueEmpty:
                break

        while True:
            try:
                message = self.private_ws_queue.get_nowait()
                await self._process_private_ws_message(message)
            except asyncio.QueueEmpty:
                break

    async def _process_orderbook_message(self, message: dict):
        self.state.last_ws_message_time = time.time()
        try:
            if "data" in message and message["topic"].startswith("orderbook"):
                data = message["data"]
                bids = data.get("b")
                asks = data.get("a")
                if bids and asks and bids[0] and asks[0] and bids[0][0] and asks[0][0]:
                    await self._update_mid_price(bids, asks)
                else:
                    self.logger.debug(
                        "Received empty or incomplete orderbook data. Skipping mid-price update."
                    )
        except Exception as e:
            self.logger.error(f"Error processing orderbook message: {e}", exc_info=True)

    async def _process_private_ws_message(self, message: dict):
        self.state.last_ws_message_time = time.time()
        try:
            if "data" in message:
                topic = message.get("topic", "")
                if topic == "order":
                    for order_data in message["data"]:
                        if order_data.get("symbol") == self.config.symbol:
                            await self._process_order_update(order_data)
                elif topic == "position":
                    for pos_data in message["data"]:
                        if pos_data["symbol"] == self.config.symbol:
                            await self._process_position_update(pos_data)
                else:
                    self.logger.debug(f"Received unknown private WS topic: {topic}")
        except Exception as e:
            self.logger.error(
                f"Error processing private WS message: {e}", exc_info=True
            )

    async def _websocket_health_check(self, current_time: float):
        ws_public_connected = (
            self.trading_client.ws_public
            and self.trading_client.ws_public.is_connected()
        )
        ws_private_connected = (
            self.trading_client.ws_private
            and self.trading_client.ws_private.is_connected()
        )

        if not ws_public_connected or not ws_private_connected:
            self.logger.warning(
                f"WebSocket {'Public' if not ws_public_connected else 'Private'} disconnected. Attempting reconnection."
            )
            await self._reconnect_websockets()
            return

        if (
            current_time - self.state.last_ws_message_time
            > self.config.system.ws_heartbeat_sec
        ):
            self.logger.warning(
                "WebSocket heartbeat lost (no new messages received). Attempting reconnection."
            )
            await self._reconnect_websockets()
            return

    async def _simulate_dry_run_price_movement(self, current_time: float):
        if self.state.mid_price == Decimal("0"):
            self.state.mid_price = Decimal("0.1")
            self.state.smoothed_mid_price = Decimal("0.1")
            self.state.price_candlestick_history.append(
                (
                    current_time,
                    self.state.mid_price,
                    self.state.mid_price,
                    self.state.mid_price,
                )
            )
            self.logger.info(
                "DRY_RUN/SIMULATION: Initializing mid_price for movement simulation."
            )

        dt = self.config.dry_run_time_step_dt
        if (current_time - self.state.last_dry_run_price_update_time) < dt:
            return

        mu = self.config.dry_run_price_drift_mu
        sigma = self.config.dry_run_price_volatility_sigma

        price_float = float(self.state.mid_price)

        if price_float <= 0:
            price_float = 1e-10

        new_price_float = price_float * np.exp(
            (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * np.random.normal()
        )

        if new_price_float < 1e-8:
            new_price_float = 1e-8

        new_mid_price = Decimal(str(new_price_float))

        async with self.market_data_lock:
            self.state.mid_price = new_mid_price

            if self.state.price_candlestick_history:
                _, high_old, low_old, _ = self.state.price_candlestick_history[-1]
                current_high = max(high_old, new_mid_price)
                current_low = min(low_old, new_mid_price)
                if (current_time - self.state.price_candlestick_history[-1][0]) < dt:
                    self.state.price_candlestick_history[-1] = (
                        current_time,
                        current_high,
                        current_low,
                        new_mid_price,
                    )
                else:
                    self.state.price_candlestick_history.append(
                        (current_time, new_mid_price, new_mid_price, new_mid_price)
                    )
            else:
                self.state.price_candlestick_history.append(
                    (current_time, new_mid_price, new_mid_price, new_mid_price)
                )

            self.state.circuit_breaker_price_points.append(
                (current_time, self.state.mid_price)
            )

            alpha = self.config.strategy.dynamic_spread.price_change_smoothing_factor
            if self.state.smoothed_mid_price == Decimal("0"):
                self.state.smoothed_mid_price = new_mid_price
            else:
                self.state.smoothed_mid_price = (alpha * new_mid_price) + (
                    (Decimal("1") - alpha) * self.state.smoothed_mid_price
                )

        self.state.last_dry_run_price_update_time = current_time
        self.logger.debug(
            f"DRY_RUN Price Movement: Mid: {self.state.mid_price}, Smoothed: {self.state.smoothed_mid_price}"
        )

    async def _simulate_dry_run_fills(self):
        orders_to_process = []
        async with self.active_orders_lock:
            for order_id, order_data in list(self.state.active_orders.items()):
                if order_id.startswith("DRY_"):
                    order_price = Decimal(str(order_data["price"]))
                    side = order_data["side"]

                    filled = False
                    if (side == "Buy" and self.state.mid_price <= order_price) or (
                        side == "Sell" and self.state.mid_price >= order_price
                    ):
                        filled = True

                    if filled:
                        fill_qty = order_data["qty"] - order_data.get("cumExecQty", Decimal("0"))
                        if fill_qty <= Decimal("0"):
                            continue

                        if (
                            side == "Sell"
                            and fill_qty > self.state.metrics.current_asset_holdings
                        ):
                            self.logger.warning(
                                f"DRY_RUN: Skipping simulated sell fill for order {order_id} (Qty: {fill_qty}) due to insufficient simulated holdings ({self.state.metrics.current_asset_holdings})."
                            )
                            continue

                        orders_to_process.append((order_id, order_data, fill_qty))

            for order_id, order_data, fill_qty in orders_to_process:
                self.logger.info(
                    f"DRY_RUN: Simulating fill for order {order_id} (Side: {order_data['side']}, Price: {order_data['price']}) with {fill_qty} at current mid_price {self.state.mid_price}"
                )

                mock_fill_data = {
                    "orderId": order_id,
                    "orderLinkId": order_data.get("orderLinkId"),
                    "symbol": order_data["symbol"],
                    "side": order_data["side"],
                    "orderType": self.config.order_type,
                    "execQty": str(fill_qty),
                    "execPrice": str(self.state.mid_price),
                    "execFee": str(
                        fill_qty
                        * self.state.mid_price
                        * self.market_info.taker_fee_rate
                    ),
                    "feeCurrency": self.config.quote_currency,
                    "pnl": "0",
                    "execType": "Trade",
                }

                async with self.active_orders_lock:
                    self.state.active_orders[order_id]["cumExecQty"] += fill_qty
                    if (
                        self.state.active_orders[order_id]["cumExecQty"]
                        >= self.state.active_orders[order_id]["qty"]
                    ):
                        self.state.active_orders[order_id]["status"] = "Filled"
                        mock_fill_data["orderStatus"] = "Filled"
                    else:
                        self.state.active_orders[order_id]["status"] = "PartiallyFilled"
                        mock_fill_data["orderStatus"] = "PartiallyFilled"

                await self._process_fill(mock_fill_data)

                if self.state.active_orders[order_id]["status"] == "Filled":
                    del self.state.active_orders[order_id]

    async def _periodic_health_check(self, current_time: float):
        if (
            current_time - self.state.last_health_check_time
        ) < self.config.system.health_check_interval_sec:
            return

        await self._update_balance_and_position()
        self.state.last_health_check_time = current_time

    async def stop(self):
        if not self.is_running:
            return
        self.is_running = False
        self.logger.info("Initiating graceful shutdown...")

        if self.config.trading_mode not in ["DRY_RUN", "SIMULATION"]:
            await self._cancel_all_orders()

        state_to_save = {
            "active_orders": {
                oid: {
                    k: str(v) if isinstance(v, Decimal) else v for k, v in odata.items()
                }
                for oid, odata in self.state.active_orders.items()
            },
            "metrics": {
                "total_trades": self.state.metrics.total_trades,
                "gross_profit": str(self.state.metrics.gross_profit),
                "gross_loss": str(self.state.metrics.gross_loss),
                "total_fees": str(self.state.metrics.total_fees),
                "wins": self.state.metrics.wins,
                "losses": self.state.metrics.losses,
                "win_rate": self.state.metrics.win_rate,
                "realized_pnl": str(self.state.metrics.realized_pnl),
                "current_asset_holdings": str(
                    self.state.metrics.current_asset_holdings
                ),
                "average_entry_price": str(self.state.metrics.average_entry_price),
                "last_pnl_update_timestamp": (
                    self.state.metrics.last_pnl_update_timestamp.isoformat()
                    if self.state.metrics.last_pnl_update_timestamp
                    else None
                ),
            },
            "is_paused": self.state.is_paused,
            "pause_end_time": self.state.pause_end_time,
            "circuit_breaker_cooldown_end_time": self.state.circuit_breaker_cooldown_end_time,
            "daily_initial_capital": str(self.state.daily_initial_capital),
            "daily_pnl_reset_date": (
                self.state.daily_pnl_reset_date.isoformat()
                if self.state.daily_pnl_reset_date
                else None
            ),
            "mid_price": str(self.state.mid_price),
            "smoothed_mid_price": str(self.state.smoothed_mid_price),
            "price_candlestick_history": [
                (t, str(h), str(l), str(c))
                for t, h, l, c in self.state.price_candlestick_history
            ],
            "circuit_breaker_price_points": [
                (t, str(p)) for t, p in self.state.circuit_breaker_price_points
            ],
        }
        try:
            await self.state_manager.save_state(state_to_save)
        except Exception as e:
            self.logger.error(
                f"Error during state saving on shutdown: {e}", exc_info=True
            )

        try:
            unrealized_pnl = self.state.metrics.calculate_unrealized_pnl(
                self.state.mid_price
            )
            daily_pnl = self.state.current_balance - self.state.daily_initial_capital
            daily_loss_pct = (
                float(abs(daily_pnl / self.state.daily_initial_capital))
                if self.state.daily_initial_capital > 0
                else 0.0
            )
            await self.db_manager.log_bot_metrics(
                self.state.metrics, unrealized_pnl, daily_pnl, daily_loss_pct
            )
        except Exception as e:
            self.logger.error(
                f"Could not log final metrics to DB. Error: {e}", exc_info=True
            )

        self.trading_client.close_websockets()
        await self.db_manager.close()
        self.logger.info("Bot shut down successfully.")

    def _schedule_coro(self, coro: Coroutine):
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self.loop)
        else:
            self.logger.warning(
                "Event loop not available or not running for scheduling coroutine from background thread. Coroutine skipped."
            )

    async def _update_mid_price(self, bids: list[list[str]], asks: list[list[str]]):
        async with self.market_data_lock:
            best_bid = Decimal(bids[0][0])
            best_ask = Decimal(asks[0][0])
            new_mid_price = (best_bid + best_ask) / Decimal("2")
            current_time = time.time()

            if new_mid_price != self.state.mid_price:
                self.state.mid_price = new_mid_price
                self.state.circuit_breaker_price_points.append(
                    (current_time, self.state.mid_price)
                )

                if self.state.price_candlestick_history:
                    last_ts, last_high, last_low, _ = (
                        self.state.price_candlestick_history[-1]
                    )
                    if (
                        current_time - last_ts
                    ) < self.config.system.loop_interval_sec * 2:
                        self.state.price_candlestick_history[-1] = (
                            current_time,
                            max(last_high, new_mid_price),
                            min(last_low, new_mid_price),
                            new_mid_price,
                        )
                    else:
                        self.state.price_candlestick_history.append(
                            (current_time, new_mid_price, new_mid_price, new_mid_price)
                        )
                else:
                    self.state.price_candlestick_history.append(
                        (current_time, new_mid_price, new_mid_price, new_mid_price)
                    )

                if self.state.smoothed_mid_price == Decimal("0"):
                    self.state.smoothed_mid_price = new_mid_price
                else:
                    alpha = (
                        self.config.strategy.dynamic_spread.price_change_smoothing_factor
                    )
                    self.state.smoothed_mid_price = (alpha * new_mid_price) + (
                        (Decimal("1") - alpha) * self.state.smoothed_mid_price
                    )

                self.logger.debug(
                    f"Mid-price updated to: {self.state.mid_price}, Smoothed: {self.state.smoothed_mid_price}"
                )

    async def _process_order_update(self, order_data: dict):
        order_id = order_data["orderId"]
        status = order_data["orderStatus"]
        cum_exec_qty = Decimal(order_data.get("cumExecQty", "0"))
        order_qty = Decimal(order_data.get("qty", "0"))

        self.logger.info(
            f"Order {order_id} status update: {status} (OrderLink: {order_data.get('orderLinkId')}), CumExecQty: {cum_exec_qty}/{order_qty}"
        )
        await self.db_manager.log_order_event(order_data)

        async with self.active_orders_lock:
            if order_id in self.state.active_orders:
                existing_order = self.state.active_orders[order_id]
                existing_order["status"] = status
                existing_order["cumExecQty"] = cum_exec_qty

                if status == "Filled" or (
                    status == "PartiallyFilled"
                    and cum_exec_qty > existing_order.get("cumExecQty", Decimal("0"))
                ):
                    pass

                if status == "Filled":
                    self.logger.info(
                        f"Order {order_id} fully filled. Removing from active orders."
                    )
                    del self.state.active_orders[order_id]
                elif status in ["Cancelled", "Rejected", "Deactivated", "Expired"]:
                    self.logger.info(
                        f"Order {order_id} removed from active orders due to status: {status}."
                    )
                    del self.state.active_orders[order_id]
            elif status == "Filled" or status == "PartiallyFilled":
                self.logger.warning(
                    f"Received fill/partial fill for untracked order {order_id}. Adding to state temporarily for processing."
                )
                self.state.active_orders[order_id] = {
                    "side": order_data.get("side"),
                    "price": Decimal(order_data.get("price", "0")),
                    "qty": order_qty,
                    "cumExecQty": cum_exec_qty,
                    "status": status,
                    "orderLinkId": order_data.get("orderLinkId"),
                    "symbol": order_data.get("symbol"),
                    "reduceOnly": order_data.get("reduceOnly", False),
                }
                if status == "Filled":
                    self.logger.info(
                        f"Order {order_id} (untracked) fully filled. Removing after processing."
                    )
                    del self.state.active_orders[order_id]
            else:
                self.logger.debug(
                    f"Received update for untracked order {order_id} with status {status}. Ignoring."
                )

    async def _process_position_update(self, pos_data: dict):
        async with self.balance_position_lock:
            new_pos_qty = Decimal(pos_data["size"]) * (
                Decimal("1") if pos_data["side"] == "Buy" else Decimal("-1")
            )
            if new_pos_qty != self.state.current_position_qty:
                self.state.current_position_qty = new_pos_qty
                self.logger.info(
                    f"POSITION UPDATE (WS): Position is now {self.state.current_position_qty} {self.config.base_currency}"
                )

            if (
                self.config.category in ["linear", "inverse"]
                and "unrealisedPnl" in pos_data
            ):
                self.state.unrealized_pnl_derivatives = Decimal(
                    pos_data["unrealisedPnl"]
                )
                self.logger.debug(
                    f"UNREALIZED PNL (WS): {self.state.unrealized_pnl_derivatives:+.4f} {self.config.quote_currency}"
                )

    async def _check_daily_loss_circuit_breaker(self) -> bool:
        cb_config = self.config.strategy.circuit_breaker
        if not cb_config.enabled or cb_config.max_daily_loss_pct <= Decimal("0"):
            return False

        current_day = datetime.now(timezone.utc).date()
        if (
            self.state.daily_pnl_reset_date is None
            or self.state.daily_pnl_reset_date.date() < current_day
        ):
            self.logger.info("New day detected. Resetting daily initial capital.")
            self.state.daily_initial_capital = self.state.current_balance
            self.state.daily_pnl_reset_date = datetime.now(timezone.utc)
            return False

        if self.state.daily_initial_capital <= Decimal("0"):
            self.logger.warning(
                "Daily initial capital is zero or negative, cannot check daily loss. Skipping."
            )
            return False

        current_total_capital = (
            self.state.current_balance
            + self.state.metrics.calculate_unrealized_pnl(self.state.mid_price)
        )

        daily_loss = self.state.daily_initial_capital - current_total_capital
        if daily_loss > (
            self.state.daily_initial_capital * cb_config.max_daily_loss_pct
        ):
            self.logger.critical(
                f"DAILY LOSS CIRCUIT BREAKER TRIPPED! Current Loss: {daily_loss:.2f} {self.config.quote_currency} "
                f"({(daily_loss / self.state.daily_initial_capital):.2%}) exceeds "
                f"max daily loss threshold ({cb_config.max_daily_loss_pct:.2%}). "
                "Shutting down for the day."
            )
            self.is_running = False
            return True
        return False

    async def _manage_orders(self):
        current_time = time.time()
        if (
            current_time - self.state.last_order_management_time
        ) < self.config.system.order_refresh_interval_sec:
            return
        self.state.last_order_management_time = current_time

        if await self._check_circuit_breaker():
            self.logger.warning("Circuit breaker tripped. Skipping order management.")
            return

        async with self.market_data_lock, self.balance_position_lock:
            if self.state.smoothed_mid_price == Decimal("0") or not self.market_info:
                self.logger.warning(
                    "Smoothed mid-price or market info not available, skipping order management."
                )
                return

        # Use the strategy to get target orders
        latest_orderbook = None
        while not self.orderbook_queue.empty():
            latest_orderbook = await self.orderbook_queue.get()
        target_bid_price, buy_qty, target_ask_price, sell_qty = self.strategy.get_target_orders(self.state, latest_orderbook)

        unrealized_pnl = self.state.metrics.calculate_unrealized_pnl(self.state.mid_price)
        if abs(unrealized_pnl) > self.state.current_balance * self.config.strategy.profit_take_threshold:
            self.logger.info(f"Profit-taking triggered: Unrealized PnL={unrealized_pnl}")
            position_qty = self.state.metrics.current_asset_holdings
            if position_qty > 0:
                await self._place_market_order("Sell", position_qty)
            elif position_qty < 0:
                await self._place_market_order("Buy", -position_qty)
        else:
            await self._reconcile_and_place_orders(target_bid_price, buy_qty, target_ask_price, sell_qty)

    async def _check_circuit_breaker(self) -> bool:
        cb_config = self.config.strategy.circuit_breaker
        if not cb_config.enabled:
            return False

        current_time = time.time()
        async with self.market_data_lock:
            recent_prices_window = [
                (t, p)
                for t, p in self.state.circuit_breaker_price_points
                if (current_time - t) <= cb_config.check_window_sec
            ]

        if len(recent_prices_window) < 2:
            return False

        recent_prices_window.sort(key=lambda x: x[0])
        start_price = recent_prices_window[0][1]
        end_price = recent_prices_window[-1][1]

        if start_price == Decimal("0"):
            return False

        price_change_pct = abs(end_price - start_price) / start_price

        if price_change_pct > cb_config.pause_threshold_pct:
            self.logger.warning(
                f"CIRCUIT BREAKER TRIPPED: Price changed {price_change_pct:.2%} in {cb_config.check_window_sec}s. Pausing trading for {cb_config.pause_duration_sec}s."
            )
            self.state.is_paused = True
            self.state.pause_end_time = current_time + cb_config.pause_duration_sec
            self.state.circuit_breaker_cooldown_end_time = (
                self.state.pause_end_time + cb_config.cool_down_after_trip_sec
            )
            await self._cancel_all_orders()
            return True
        return False







    async def _reconcile_and_place_orders(
        self, target_bid: Decimal, buy_qty: Decimal, target_ask: Decimal, sell_qty: Decimal
    ):
        if not self.market_info:
            return

        target_bid = self.market_info.format_price(target_bid)
        target_ask = self.market_info.format_price(target_ask)

        current_active_orders_by_side = {"Buy": [], "Sell": []}
        orders_to_cancel = []

        async with self.active_orders_lock:
            for order_id, order_data in list(self.state.active_orders.items()):
                if order_data.get("symbol") != self.config.symbol:
                    self.logger.warning(
                        f"Found untracked symbol order {order_id} in active_orders. Cancelling."
                    )
                    orders_to_cancel.append((order_id, order_data.get("orderLinkId")))
                    continue

                if order_data["status"] in [
                    "Filled",
                    "PartiallyFilled",
                    "Cancelled",
                    "Rejected",
                    "Deactivated",
                    "Expired",
                ]:
                    if order_data["qty"] == order_data.get(
                        "cumExecQty", Decimal("0")
                    ):
                        self.logger.debug(
                            f"Removing fully processed order {order_id} from active orders."
                        )
                        del self.state.active_orders[order_id]
                    else:
                        if order_data["status"] in [
                            "Cancelled",
                            "Rejected",
                            "Deactivated",
                            "Expired",
                        ]:
                            self.logger.debug(
                                f"Removing partially filled but inactive order {order_id} from active orders."
                            )
                            del self.state.active_orders[order_id]
                        else:
                            current_active_orders_by_side[order_data["side"]].append(
                                (order_id, order_data, False)
                            )
                    continue

                is_stale = False
                if order_data["side"] == "Buy":
                    if abs(order_data["price"] - target_bid) > (
                        order_data["price"]
                        * self.config.strategy.order_stale_threshold_pct
                    ):
                        is_stale = True
                    current_active_orders_by_side["Buy"].append(
                        (order_id, order_data, is_stale)
                    )
                else:
                    if abs(order_data["price"] - target_ask) > (
                        order_data["price"]
                        * self.config.strategy.order_stale_threshold_pct
                    ):
                        is_stale = True
                    current_active_orders_by_side["Sell"].append(
                        (order_id, order_data, is_stale)
                    )

            bid_order_to_keep = None
            for oid, odata, is_stale in current_active_orders_by_side["Buy"]:
                if not is_stale and bid_order_to_keep is None:
                    bid_order_to_keep = odata
                else:
                    orders_to_cancel.append((oid, odata.get("orderLinkId")))

            ask_order_to_keep = None
            for oid, odata, is_stale in current_active_orders_by_side["Sell"]:
                if not is_stale and ask_order_to_keep is None:
                    ask_order_to_keep = odata
                else:
                    orders_to_cancel.append((oid, odata.get("orderLinkId")))

        for oid, olid in orders_to_cancel:
            order_info = self.state.active_orders.get(oid, {})
            self.logger.info(
                f"Cancelling stale/duplicate order {oid} (Side: {order_info.get('side')}, Price: {order_info.get('price')}). Target Bid: {target_bid}, Target Ask: {target_ask}"
            )
            await self._cancel_order(oid, olid)

        new_orders_to_place = []

        current_outstanding_orders = 0
        async with self.active_orders_lock:
            for order_id, order_data in self.state.active_orders.items():
                if order_data["status"] not in [
                    "Filled",
                    "Cancelled",
                    "Rejected",
                    "Deactivated",
                    "Expired",
                ]:
                    current_outstanding_orders += 1

        if (
            not bid_order_to_keep
            and current_outstanding_orders < self.config.strategy.max_outstanding_orders
        ):

            if buy_qty > 0:
                new_orders_to_place.append(("Buy", target_bid, buy_qty))
                current_outstanding_orders += 1
            else:
                self.logger.debug(
                    "Calculated buy quantity is zero or too small, skipping bid order placement."
                )

        if (
            not ask_order_to_keep
            and current_outstanding_orders < self.config.strategy.max_outstanding_orders
        ):
            if sell_qty > 0:
                new_orders_to_place.append(("Sell", target_ask, sell_qty))
            else:
                self.logger.debug(
                    "Calculated sell quantity is zero or too small, skipping ask order placement."
                )
        elif not ask_order_to_keep:
            self.logger.warning(
                f"Skipping ask order placement: Max outstanding orders ({self.config.strategy.max_outstanding_orders}) reached or will be exceeded."
            )

        for side, price, qty in new_orders_to_place:
            self.logger.info(f"Placing new {side} order: Price={price}, Qty={qty}")
            await self._place_limit_order(side, price, qty)

    async def _log_status_summary(self):
        async with self.balance_position_lock, self.active_orders_lock, self.market_data_lock:
            metrics = self.state.metrics
            current_market_price = (
                self.state.mid_price
                if self.state.mid_price > Decimal("0")
                else self.state.smoothed_mid_price
            )

            if current_market_price == Decimal("0"):
                self.logger.warning(
                    "Cannot calculate unrealized PnL, current market price is zero."
                )
                unrealized_pnl_bot_calculated = Decimal("0")
            else:
                unrealized_pnl_bot_calculated = metrics.calculate_unrealized_pnl(
                    current_market_price
                )

            if self.config.category in ["linear", "inverse"]:
                display_unrealized_pnl = self.state.unrealized_pnl_derivatives
            else:
                display_unrealized_pnl = unrealized_pnl_bot_calculated

            total_current_pnl = metrics.net_realized_pnl + display_unrealized_pnl
            pos_qty = metrics.current_asset_holdings
            exposure_usd = (
                pos_qty * current_market_price
                if current_market_price > Decimal("0")
                else Decimal("0")
            )

            daily_pnl = (
                self.state.current_balance
                + display_unrealized_pnl
                - self.state.daily_initial_capital
            )
            daily_loss_pct = (
                float(abs(daily_pnl / self.state.daily_initial_capital))
                if self.state.daily_initial_capital > 0 and daily_pnl < 0
                else 0.0
            )

            pnl_summary = (
                f"Realized PNL: {metrics.realized_pnl:+.4f} {self.config.quote_currency} | "
                f"Unrealized PNL: {display_unrealized_pnl:+.4f} {self.config.quote_currency}"
            )

            active_buys = sum(
                1
                for o in self.state.active_orders.values()
                if o["side"] == "Buy"
                and o["status"]
                not in ["Filled", "Cancelled", "Rejected", "Deactivated", "Expired"]
            )
            active_sells = sum(
                1
                for o in self.state.active_orders.values()
                if o["side"] == "Sell"
                and o["status"]
                not in ["Filled", "Cancelled", "Rejected", "Deactivated", "Expired"]
            )

        self.logger.info(
            f"STATUS | Total Current PNL: {total_current_pnl:+.4f} | {pnl_summary} | "
            f"Net Realized PNL: {metrics.net_realized_pnl:+.4f} | Daily PNL: {daily_pnl:+.4f} ({daily_loss_pct:.2%}) | "
            f"Win Rate: {metrics.win_rate:.2f}% | Position: {pos_qty} {self.config.base_currency} (Exposure: {exposure_usd:+.2f} {self.config.quote_currency}) | "
            f"Fees: Maker {metrics.maker_fees:.4f}, Taker {metrics.taker_fees:.4f} | "
            f"Orders: {active_buys} Buy / {active_sells} Sell"
        )
        await self.db_manager.log_bot_metrics(
            metrics, display_unrealized_pnl, daily_pnl, daily_loss_pct
        )

    async def _fetch_market_info(self) -> bool:
        if self.config.trading_mode == "SIMULATION":
            self.market_info = MarketInfo(
                symbol=self.config.symbol,
                price_precision=Decimal("0.00001"),
                quantity_precision=Decimal("1"),
                min_order_qty=Decimal("1"),
                min_notional_value=self.config.min_order_value_usd,
                maker_fee_rate=Decimal("0.0002"),
                taker_fee_rate=Decimal("0.0005"),
            )
            self.logger.info(
                f"SIMULATION mode: Mock market info loaded for {self.config.symbol}: {self.market_info}"
            )
            return True

        info = await self.trading_client.get_instruments_info()
        if not info:
            self.logger.critical(
                "Failed to retrieve instrument info from API. Check symbol and connectivity."
            )
            return False

        # Extract fee rates with robust defaults
        maker_fee_rate_str = info.get("makerFeeRate")
        taker_fee_rate_str = info.get("takerFeeRate")

        default_maker_fee = Decimal("0.0002")
        default_taker_fee = Decimal("0.0005")

        if maker_fee_rate_str is None:
            if taker_fee_rate_str is not None:
                self.logger.warning(
                    f"Missing 'makerFeeRate' for {self.config.symbol}. Using 'takerFeeRate' as fallback for maker fee. Full info: {info}"
                )
                maker_fee_rate = Decimal(taker_fee_rate_str)
            else:
                self.logger.warning(
                    f"Missing 'makerFeeRate' and 'takerFeeRate' for {self.config.symbol}. Using default maker fee: {default_maker_fee}. Full info: {info}"
                )
                maker_fee_rate = default_maker_fee
        else:
            maker_fee_rate = Decimal(maker_fee_rate_str)

        if taker_fee_rate_str is None:
            self.logger.warning(
                f"Missing 'takerFeeRate' for {self.config.symbol}. Using default taker fee: {default_taker_fee}. Full info: {info}"
            )
            taker_fee_rate = default_taker_fee
        else:
            taker_fee_rate = Decimal(taker_fee_rate_str)

        try:
            price_precision = Decimal(info["priceFilter"]["tickSize"])
            quantity_precision = Decimal(info["lotSizeFilter"]["qtyStep"])
            min_order_qty = Decimal(info["lotSizeFilter"]["minOrderQty"])
            min_notional_value = Decimal(
                info["lotSizeFilter"].get("minNotionalValue", "0")
            )
        except KeyError as e:
            self.logger.critical(
                f"Critical market info missing for {self.config.symbol} (e.g., priceFilter, lotSizeFilter): {e}. Full info: {info}",
                exc_info=True,
            )
            return False
        except Exception as e:
            self.logger.critical(
                f"Unexpected error parsing critical market info for {self.config.symbol}: {e}. Full info: {info}",
                exc_info=True,
            )
            return False

        self.market_info = MarketInfo(
            symbol=self.config.symbol,
            price_precision=price_precision,
            quantity_precision=quantity_precision,
            min_order_qty=min_order_qty,
            min_notional_value=min_notional_value,
            maker_fee_rate=maker_fee_rate,
            taker_fee_rate=taker_fee_rate,
        )
        if self.market_info.min_notional_value == Decimal("0"):
            self.logger.warning(
                f"minNotionalValue not found or is 0 for {self.config.symbol}. Using config.min_order_value_usd as fallback."
            )
            self.market_info.min_notional_value = self.config.min_order_value_usd

        self.logger.info(
            f"Market info fetched for {self.config.symbol}: {self.market_info}"
        )
        return True

    async def _update_balance_and_position(self) -> bool:
        async with self.balance_position_lock:
            if self.config.trading_mode in ["DRY_RUN", "SIMULATION"]:
                if self.state.current_balance == Decimal("0"):
                    self.state.current_balance = self.config.initial_dry_run_capital
                    self.state.available_balance = self.state.current_balance
                    self.logger.info(
                        f"{self.config.trading_mode}: Initialized virtual balance: {self.state.current_balance} {self.config.quote_currency}"
                    )
                self.state.current_position_qty = (
                    self.state.metrics.current_asset_holdings
                )
                self.state.unrealized_pnl_derivatives = Decimal("0")
                return True

            balance_data = await self.trading_client.get_wallet_balance()
            if not balance_data:
                self.logger.error("Failed to fetch wallet balance.")
                return False

            found_quote_balance = False
            for coin in balance_data.get("coin", []):
                if coin["coin"] == self.config.quote_currency:
                    self.state.current_balance = Decimal(coin["walletBalance"])
                    self.state.available_balance = Decimal(
                        coin.get("availableToWithdraw", coin["walletBalance"])
                    )
                    self.logger.debug(
                        f"Balance: {self.state.current_balance} {self.config.quote_currency}, Available: {self.state.available_balance}"
                    )
                    await self.db_manager.log_balance_update(
                        self.config.quote_currency,
                        self.state.current_balance,
                        self.state.available_balance,
                    )
                    found_quote_balance = True
                    break

            if not found_quote_balance:
                self.logger.warning(
                    f"Could not find balance for {self.config.quote_currency}. This might affect order sizing."
                )

            if self.config.category in ["linear", "inverse"]:
                position_data = await self.trading_client.get_position_info()
                if position_data and position_data.get("size"):
                    self.state.current_position_qty = Decimal(position_data["size"]) * (
                        Decimal("1")
                        if position_data["side"] == "Buy"
                        else Decimal("-1")
                    )
                    self.state.unrealized_pnl_derivatives = Decimal(
                        position_data.get("unrealisedPnl", "0")
                    )
                else:
                    self.state.current_position_qty = Decimal("0")
                    self.state.unrealized_pnl_derivatives = Decimal("0")
            else:
                self.state.current_position_qty = (
                    self.state.metrics.current_asset_holdings
                )
                self.state.unrealized_pnl_derivatives = Decimal("0")

            self.logger.info(
                f"Updated Balance: {self.state.current_balance} {self.config.quote_currency}, Position: {self.state.current_position_qty} {self.config.base_currency}, UPNL (Deriv): {self.state.unrealized_pnl_derivatives:+.4f}"
            )
            return True

    async def _process_fill(self, trade_data: dict):
        side = trade_data.get("side", "Unknown")
        exec_qty = Decimal(trade_data.get("execQty", "0"))
        exec_price = Decimal(trade_data.get("execPrice", "0"))
        exec_fee = Decimal(trade_data.get("execFee", "0"))

        metrics = self.state.metrics
        liquidity_role = trade_data.get("execType", "Taker")
        self.state.metrics.update_fee_metrics(exec_fee, liquidity_role)
        realized_pnl_impact = Decimal("0")

        if side == "Buy":
            metrics.update_position_and_pnl(side, exec_qty, exec_price)
            if self.config.trading_mode in ["DRY_RUN", "SIMULATION"]:
                self.state.current_balance -= (exec_qty * exec_price) + exec_fee
                self.state.available_balance = self.state.current_balance
            self.logger.info(
                f"Order FILLED: BUY {exec_qty} @ {exec_price}, Fee: {exec_fee}. Holdings: {metrics.current_asset_holdings}, Avg Entry: {metrics.average_entry_price}"
            )
        elif side == "Sell":
            profit_loss_on_sale = (exec_price - metrics.average_entry_price) * exec_qty
            metrics.update_position_and_pnl(side, exec_qty, exec_price)
            realized_pnl_impact = profit_loss_on_sale
            if self.config.trading_mode in ["DRY_RUN", "SIMULATION"]:
                self.state.current_balance += (exec_qty * exec_price) - exec_fee
                self.state.available_balance = self.state.current_balance
            self.logger.info(
                f"Order FILLED: SELL {exec_qty} @ {exec_price}, Fee: {exec_fee}. Realized PnL from sale: {profit_loss_on_sale:+.4f}. Holdings: {metrics.current_asset_holdings}, Avg Entry: {metrics.average_entry_price}"
            )
        else:
            self.logger.warning(
                f"Unknown side '{side}' for fill. Cannot update PnL metrics."
            )

        metrics.total_trades += 1
        metrics.total_fees += exec_fee
        if realized_pnl_impact > 0:
            metrics.gross_profit += realized_pnl_impact
            metrics.wins += 1
        elif realized_pnl_impact < 0:
            metrics.gross_loss += abs(realized_pnl_impact)
            metrics.losses += 1
        metrics.update_win_rate()

        await self.db_manager.log_trade_fill(trade_data, realized_pnl_impact)
        await self._update_balance_and_position()

    async def _cancel_order(self, order_id: str, order_link_id: str | None = None):
        self.logger.info(
            f"Attempting to cancel order {order_id} (OrderLink: {order_link_id})..."
        )
        if self.config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            self.logger.info(
                f"{self.config.trading_mode}: Would cancel order {order_id}."
            )
            async with self.active_orders_lock:
                if order_id in self.state.active_orders:
                    del self.state.active_orders[order_id]
            return

        try:
            if await self.trading_client.cancel_order(order_id, order_link_id):
                self.logger.info(f"Order {order_id} cancelled successfully.")
                async with self.active_orders_lock:
                    if order_id in self.state.active_orders:
                        del self.state.active_orders[order_id]
            else:
                self.logger.error(
                    f"Failed to cancel order {order_id} via API after retries."
                )
        except Exception as e:
            self.logger.error(
                f"Error during cancellation of order {order_id}: {e}", exc_info=True
            )

    async def _cancel_all_orders(self):
        self.logger.info("Canceling all open orders...")
        if self.config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            self.logger.info(
                f"{self.config.trading_mode}: Would cancel all open orders."
            )
        else:
            try:
                if await self.trading_client.cancel_all_orders():
                    self.logger.info("All orders cancelled successfully.")
                else:
                    self.logger.error(
                        "Failed to cancel all orders via API after retries."
                    )
            except Exception as e:
                self.logger.error(
                    f"Error during cancellation of all orders: {e}", exc_info=True
                )

        async with self.active_orders_lock:
            self.state.active_orders.clear()



    async def _place_limit_order(self, side: str, price: Decimal, quantity: Decimal):
        if not self.market_info:
            self.logger.error("Cannot place order, market info not available.")
            raise OrderPlacementError("Market information is not available.")

        qty_f, price_f = self.market_info.format_quantity(
            quantity
        ), self.market_info.format_price(price)
        if qty_f <= Decimal("0") or price_f <= Decimal("0"):
            self.logger.warning(
                f"Attempted to place order with zero or negative quantity/price: Qty={qty_f}, Price={price_f}. Skipping."
            )
            return

        order_notional_value = qty_f * price_f
        min_notional = max(
            self.market_info.min_notional_value, self.config.min_order_value_usd
        )
        if order_notional_value < min_notional:
            self.logger.warning(
                f"Calculated order notional value {order_notional_value:.2f} is below minimum {min_notional:.2f}. Skipping order placement."
            )
            return

        order_link_id = f"mm_{side}_{int(time.time() * 1000)}"

        params = {
            "category": self.config.category,
            "symbol": self.config.symbol,
            "side": side,
            "orderType": self.config.order_type,
            "qty": str(qty_f),
            "price": str(price_f),
            "timeInForce": "PostOnly",  # Enforce PostOnly
            "orderLinkId": order_link_id,
        }

        if self.config.category in ["linear", "inverse"]:
            async with self.balance_position_lock:
                current_position = self.state.current_position_qty
            if (side == "Sell" and current_position > Decimal("0")) or (
                side == "Buy" and current_position < Decimal("0")
            ):
                params["reduceOnly"] = True
                self.logger.debug(
                    f"Setting reduceOnly=True for {side} order (current position: {current_position})."
                )

        if self.config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            oid = f"DRY_{side}_{int(time.time() * 1000)}"
            self.logger.info(
                f"{self.config.trading_mode}: Would place {side} order: ID={oid}, Qty={qty_f}, Price={price_f}"
            )
            async with self.active_orders_lock:
                self.state.active_orders[oid] = {
                    "side": side,
                    "price": price_f,
                    "qty": qty_f,
                    "cumExecQty": Decimal("0"),
                    "status": "New",
                    "orderLinkId": order_link_id,
                    "symbol": self.config.symbol,
                    "reduceOnly": params.get("reduceOnly", False),
                }
            await self.db_manager.log_order_event(
                {**params, "orderId": oid, "orderStatus": "New", "cumExecQty": "0"},
                f"{self.config.trading_mode} Order placed",
            )
            return

        try:
            result = await self.trading_client.place_order(params)
            if result and result.get("orderId"):
                oid = result["orderId"]
                self.logger.info(
                    f"Placed {side} post-only order: ID={oid}, Price={price_f}, Qty={qty_f}"
                )
                async with self.active_orders_lock:
                    self.state.active_orders[oid] = {
                        "side": side,
                        "price": price_f,
                        "qty": qty_f,
                        "cumExecQty": Decimal("0"),
                        "status": "New",
                        "orderLinkId": order_link_id,
                        "symbol": self.config.symbol,
                        "reduceOnly": params.get("reduceOnly", False),
                    }
                await self.db_manager.log_order_event(
                    {**params, "orderId": oid, "orderStatus": "New", "cumExecQty": "0"},
                    "Post-only order placed",
                )
            else:
                self.logger.warning(
                    f"Post-only order rejected for {side} at {price_f}. Retrying with adjusted price."
                )
                # Adjust price slightly and retry
                adjusted_price = price_f * (Decimal("0.999") if side == "Buy" else Decimal("1.001"))
                await self._place_limit_order(side, adjusted_price, qty_f)
        except BybitAPIError as e:
            self.logger.error(f"Failed to place post-only order: {e}")
            raise OrderPlacementError(f"Failed to place {side} post-only order.")

    async def _place_market_order(self, side: str, quantity: Decimal):
        """Place a market order to take profit."""
        qty_f = self.market_info.format_quantity(quantity)
        if qty_f <= Decimal("0"):
            self.logger.warning(f"Invalid market order quantity: {qty_f}. Skipping.")
            return

        params = {
            "category": self.config.category,
            "symbol": self.config.symbol,
            "side": side,
            "orderType": "Market",
            "qty": str(qty_f),
            "reduceOnly": True,
        }
        if self.config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            oid = f"DRY_MKT_{side}_{int(time.time() * 1000)}"
            self.logger.info(
                f"{self.config.trading_mode}: Would place market {side} order: Qty={qty_f}"
            )
            await self._process_fill({
                "orderId": oid,
                "symbol": self.config.symbol,
                "side": side,
                "execQty": str(qty_f),
                "execPrice": str(self.state.mid_price),
                "execFee": str(qty_f * self.state.mid_price * self.market_info.taker_fee_rate),
                "feeCurrency": self.config.quote_currency,
                "execType": "Taker",
            })
            return

        result = await self.trading_client.place_order(params)
        if result and result.get("orderId"):
            self.logger.info(f"Placed market {side} order: Qty={qty_f}")
        else:
            self.logger.error(f"Failed to place market {side} order: Qty={qty_f}")

    async def _reconcile_orders_on_startup(self):
        if self.config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            self.logger.info(
                f"{self.config.trading_mode} mode: Skipping order reconciliation."
            )
            return

        self.logger.info("Reconciling active orders with exchange...")
        try:
            exchange_orders = {
                o["orderId"]: o for o in await self.trading_client.get_open_orders()
            }
        except Exception as e:
            self.logger.error(
                f"Failed to fetch open orders from exchange during reconciliation: {e}. Proceeding with local state only.",
                exc_info=True,
            )
            exchange_orders = {}

        async with self.active_orders_lock:
            local_ids = set(self.state.active_orders.keys())
            exchange_ids = set(exchange_orders.keys())

            for oid in local_ids - exchange_ids:
                self.logger.warning(
                    f"Local order {oid} not found on exchange. Removing from local state."
                )
                del self.state.active_orders[oid]

            for oid in exchange_ids - local_ids:
                o = exchange_orders[oid]
                self.logger.warning(
                    f"Exchange order {oid} ({o['side']} {o['qty']} @ {o['price']}) not in local state. Adding."
                )
                self.state.active_orders[oid] = {
                    "side": o["side"],
                    "price": Decimal(o["price"]),
                    "qty": Decimal(o["qty"]),
                    "cumExecQty": Decimal(o.get("cumExecQty", "0")),
                    "status": o["orderStatus"],
                    "orderLinkId": o.get("orderLinkId"),
                    "symbol": o.get("symbol"),
                    "reduceOnly": o.get("reduceOnly", False),
                }

            for oid in local_ids.intersection(exchange_ids):
                local_order = self.state.active_orders[oid]
                exchange_order = exchange_orders[oid]

                if local_order["status"] != exchange_order[
                    "orderStatus"
                ] or local_order.get("cumExecQty", Decimal("0")) != Decimal(
                    exchange_order.get("cumExecQty", "0")
                ):
                    self.logger.info(
                        f"Order {oid} status/cumExecQty mismatch. Updating from {local_order['status']}/{local_order.get('cumExecQty', Decimal('0'))} to {exchange_order['orderStatus']}/{exchange_order.get('cumExecQty', '0')}."
                    )
                    local_order["status"] = exchange_order["orderStatus"]
                    local_order["cumExecQty"] = Decimal(
                        exchange_order.get("cumExecQty", "0")
                    )

        self.logger.info(
            f"Order reconciliation complete. {len(self.state.active_orders)} active orders after reconciliation."
        )


if __name__ == "__main__":
    bot = None
    try:
        config = Config()
        bot = BybitMarketMaker(config)
        asyncio.run(bot.run())
    except (KeyboardInterrupt, SystemExit):
        print("\nBot stopped by user.")
    except (
        ValueError,
        APIAuthError,
        MarketInfoError,
        InitialBalanceError,
        WebSocketConnectionError,
        ConfigurationError,
        OrderPlacementError,
        BybitAPIError,
        BybitRateLimitError,
        BybitInsufficientBalanceError,
    ) as e:
        error_type = type(e).__name__
        logger = bot.logger if bot else logging.getLogger("MarketMakerBot")
        logger.critical(f"Critical Error ({error_type}): {e}", exc_info=True)
        print(f"\nCritical Error ({error_type}): {e}. Check log file for details.")
        sys.exit(1)
    except Exception as e:
        logger = bot.logger if bot else logging.getLogger("MarketMakerBot")
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
        print(
            f"\nAn unexpected critical error occurred during bot runtime: {e}. Check log file for details."
        )
        sys.exit(1)
