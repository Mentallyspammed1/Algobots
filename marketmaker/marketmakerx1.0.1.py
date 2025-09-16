import asyncio
import logging
import os
import signal
import statistics
import time
import uuid
import warnings
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import (
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_UP,
    Decimal,
    DivisionByZero,
    InvalidOperation,
)
from pathlib import Path
from typing import Any

import orjson as json

# --- Optional TA deps (pandas + pandas_ta) ---
try:
    import pandas as pd
    import pandas_ta as pta
    PANDAS_TA_AVAILABLE = True
except Exception:
    pd = None
    pta = None
    PANDAS_TA_AVAILABLE = False

# Optional: suppress pkg_resources deprecation warnings from dependencies
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pkg_resources")

# --- Dependency Imports ---
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket
from rich.console import Console
from rich.live import Live
from rich.logging import RichHandler
from rich.table import Table

# =========================
# Logging setup (with symbol context)
# =========================
console = Console()

_old_factory = logging.getLogRecordFactory()
def _record_factory(*args, **kwargs):
    record = _old_factory(*args, **kwargs)
    if not hasattr(record, "symbol"):
        record.symbol = "-"
    return record
logging.setLogRecordFactory(_record_factory)

logging.basicConfig(
    level="INFO",
    format="[%(asctime)s] [%(levelname)s] [%(symbol)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[RichHandler(markup=True, rich_tracebacks=True)]
)
logger = logging.getLogger("rich")


class ContextFilter(logging.Filter):
    def __init__(self, symbol: str):
        super().__init__()
        self.symbol = symbol

    def filter(self, record):
        record.symbol = self.symbol
        return True


# =========================
# Helpers: Decimal math, rounding, tolerances
# =========================
def to_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)

def clamp_decimal(x: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return min(hi, max(lo, x))

def round_to_increment(x: Decimal, inc: Decimal, rounding=ROUND_HALF_UP) -> Decimal:
    if inc <= 0:
        return x
    try:
        return (x / inc).to_integral_value(rounding=rounding) * inc
    except (InvalidOperation, DivisionByZero):
        return x

def floor_to_increment(x: Decimal, inc: Decimal) -> Decimal:
    return round_to_increment(x, inc, rounding=ROUND_FLOOR)

def ceil_to_increment(x: Decimal, inc: Decimal) -> Decimal:
    return round_to_increment(x, inc, rounding=ROUND_CEILING)

def approx_equal(a: Decimal, b: Decimal, tol: Decimal) -> bool:
    return abs(a - b) <= tol


# =========================
# Data Structures & State
# =========================
@dataclass
class InstrumentInfo:
    tick_size: Decimal
    step_size: Decimal
    min_order_size: Decimal
    price_precision: int = field(init=False)
    qty_precision: int = field(init=False)

    def __post_init__(self):
        self.price_precision = max(0, abs(self.tick_size.as_tuple().exponent))
        self.qty_precision = max(0, abs(self.step_size.as_tuple().exponent))

@dataclass
class BotState:
    instrument_info: InstrumentInfo | None = None
    recent_prices: deque = field(default_factory=lambda: deque(maxlen=240))  # last ~4 minutes @1s
    consecutive_api_failures: int = 0
    is_circuit_breaker_active: bool = False
    last_mid_price: Decimal | None = None
    last_quote_prices: dict[str, Decimal] = field(default_factory=dict)


# =========================
# Position Manager
# =========================
class PositionManager:
    def __init__(self, config, api):
        self.config = config
        self.api = api
        self.size = Decimal("0")
        self.avg_entry_price = Decimal("0")
        self.unrealized_pnl = Decimal("0")
        self.realized_pnl = Decimal("0")

    def _safe_decimal(self, value: Any, default: str = "0.0") -> Decimal:
        return to_decimal(value, default)

    def update_position(self, data: dict):
        self.size = self._safe_decimal(data.get('size'))
        self.avg_entry_price = self._safe_decimal(data.get('avgPrice'))
        self.unrealized_pnl = self._safe_decimal(data.get('unrealisedPnl'))

    def process_real_fill(self, trade: dict):
        closed_pnl = self._safe_decimal(trade.get('closedPnl'))
        if closed_pnl != Decimal("0"):
            self.realized_pnl += closed_pnl
            logger.info(f"Trade executed. Closed PnL: {closed_pnl:.4f}, Total Realized: {self.realized_pnl:.4f}")

    def process_virtual_fill(self, side: str, price: Decimal, qty: Decimal):
        if qty <= 0:
            return

        old_size = self.size
        current_value = self.size * self.avg_entry_price if self.size != 0 else Decimal("0")
        direction = Decimal("1") if side == "Buy" else Decimal("-1")
        fill_value = direction * qty * price
        new_position_size = self.size + (qty if side == "Buy" else -qty)

        # Realize partial PnL on reductions
        if self.size == 0:
            self.avg_entry_price = price
            self.unrealized_pnl = Decimal("0")
        elif (self.size > 0 and side == "Sell") or (self.size < 0 and side == "Buy"):
            reduce_qty = min(abs(self.size), qty)
            if reduce_qty > 0 and self.avg_entry_price > 0:
                pnl_per_unit = (price - self.avg_entry_price) if self.size > 0 else (self.avg_entry_price - price)
                realized_component = pnl_per_unit * reduce_qty
                self.realized_pnl += realized_component
                logger.info(f"[DRY RUN] Realized PnL: {realized_component:.4f}, Total: {self.realized_pnl:.4f}")

        if new_position_size == 0:
            self.unrealized_pnl = Decimal("0")
            self.avg_entry_price = Decimal("0")
        else:
            if (self.size >= 0 and new_position_size > 0) or (self.size <= 0 and new_position_size < 0):
                try:
                    self.avg_entry_price = abs((current_value + fill_value) / new_position_size)
                except (InvalidOperation, DivisionByZero):
                    self.avg_entry_price = price
            else:
                self.avg_entry_price = price

        self.size = new_position_size
        logger.info(f"[DRY RUN] Fill: {side} {qty} @ {price}. Position: {old_size} → {self.size}")

    def refresh_unrealized_pnl(self, mid: Decimal):
        if self.size == 0 or self.avg_entry_price == 0:
            self.unrealized_pnl = Decimal("0")
            return
        self.unrealized_pnl = (mid - self.avg_entry_price) * self.size

    async def check_and_manage_risk(self, state: BotState):
        if self.size == Decimal("0"):
            return False

        try:
            position_value = abs(self.size) * (self.avg_entry_price if self.avg_entry_price != 0 else Decimal("1"))
            pnl_pct = self.unrealized_pnl / position_value if position_value > 0 else Decimal("0")
        except (InvalidOperation, DivisionByZero):
            pnl_pct = Decimal("0")

        tp_pct = Decimal(str(self.config['risk_management']['take_profit_pct']))
        sl_pct = Decimal(str(self.config['risk_management']['stop_loss_pct']))

        should_close, reason = False, ""
        if pnl_pct >= tp_pct:
            should_close, reason = True, f"Take Profit ({float(pnl_pct):.2%})"
        elif pnl_pct <= -sl_pct:
            should_close, reason = True, f"Stop Loss ({float(pnl_pct):.2%})"

        if should_close:
            logger.warning(f"[bold yellow]Risk Manager: Closing position - {reason}[/bold yellow]")
            logger.warning(f"Position: {self.size}, Unrealized PnL: {self.unrealized_pnl:.4f}")
            side_to_close = "Buy" if self.size < 0 else "Sell"
            qty_to_close = abs(self.size)
            await self.api.close_position(side_to_close, qty_to_close)
            return True
        return False


# =========================
# Core Bot Class
# =========================
class EnhancedBybitMarketMaker:
    def __init__(self, config):
        self.config = config
        self.state = BotState()

        # Load .env file from script directory
        script_dir = Path(__file__).parent
        env_path = script_dir / '.env'
        if env_path.exists():
            load_dotenv(env_path)
            logger.info(f"Loaded .env from {env_path}")
        else:
            load_dotenv()
            logger.warning(f".env not found at {env_path}, trying default locations")

        # Fallback to config credentials if present
        self.api_key = os.getenv('BYBIT_API_KEY') or str(config.get("credentials", {}).get("api_key", "")).strip()
        self.api_secret = os.getenv('BYBIT_API_SECRET') or str(config.get("credentials", {}).get("api_secret", "")).strip()

        if not self.api_key or not self.api_secret:
            logger.error(f"Current directory: {os.getcwd()}")
            logger.error(f"Script directory: {script_dir}")
            logger.error(f".env exists at {env_path}: {env_path.exists()}")
            raise ValueError("API keys not found. Ensure a .env file exists with BYBIT_API_KEY and BYBIT_API_SECRET.")

        # HTTP session
        self.session = HTTP(
            testnet=config['testnet'],
            api_key=self.api_key,
            api_secret=self.api_secret,
            recv_window=10000,
            timeout=30
        )

        self.api = self
        self.position_manager = PositionManager(config, self)
        self.orderbook: dict[str, dict[Decimal, Decimal]] = {"bids": {}, "asks": {}}
        self.active_orders: dict[str, dict] = {}
        self.virtual_orders: dict[str, dict] = {}
        self.last_reprice_time = 0.0

        # Repricing sensitivity with defaults
        self.price_tol_ticks = Decimal(str(config['order_management'].get('price_tolerance_ticks', 0.5)))
        self.qty_tol_steps = Decimal(str(config['order_management'].get('qty_tolerance_steps', 0)))
        self.mid_drift_threshold = Decimal(str(config['order_management'].get('mid_drift_threshold_ticks', 0.5)))

        # TA configuration and state
        ta_cfg_default = {
            "enabled": False,
            "rsi_length": 14,
            "ema_fast": 12,
            "ema_slow": 26,
            "bb_length": 20,
            "bb_std": 2.0,
            "signal_fair_value_bps": 2.0,  # up to +/- 2 bps shift by RSI signal
            "bb_spread_mult": 0.5,        # widen spread proportional to BB width % * this
            "qty_bias_max": 0.5           # up to +50% qty on favored side
        }
        self.ta_cfg = {**ta_cfg_default, **(config.get("ta") or {})}
        self.ta_enabled = bool(self.ta_cfg.get("enabled") and PANDAS_TA_AVAILABLE)
        if self.ta_cfg.get("enabled") and not PANDAS_TA_AVAILABLE:
            logger.warning("TA enabled in config but pandas/pandas_ta not installed. TA features disabled.")
        self.ta_state: dict[str, float | None] = {
            "rsi": None,
            "ema_fast": None,
            "ema_slow": None,
            "bb_width_pct": None,  # (upper-lower)/middle
        }

        # Add symbol context filter to logger
        logger.addFilter(ContextFilter(config['symbol']))

        # Rate limit backoff
        self._rate_limit_backoff_sec = 2.0
        self._max_backoff_sec = 30.0

        # Hold references to pybit websockets
        self.ws_public: WebSocket | None = None
        self.ws_private: WebSocket | None = None

        # Will be set in run()
        self.loop: asyncio.AbstractEventLoop | None = None

    # ------------- REST call wrapper -------------
    async def _api_call(self, method, **kwargs):
        if self.state.is_circuit_breaker_active:
            logger.warning("API call blocked by circuit breaker.")
            return None

        try:
            response = await asyncio.to_thread(method, **kwargs)
            if response and response.get('retCode') == 0:
                self.state.consecutive_api_failures = 0
                self._rate_limit_backoff_sec = 2.0
                return response['result']
            else:
                msg = response.get('retMsg', 'Unknown error') if response else "No response"
                code = response.get('retCode') if response else None

                if code == 10006 or (msg and "rate" in str(msg).lower()):
                    logger.warning(f"Rate limit hit. Backing off {self._rate_limit_backoff_sec}s.")
                    await asyncio.sleep(self._rate_limit_backoff_sec)
                    self._rate_limit_backoff_sec = min(self._rate_limit_backoff_sec * 2, self._max_backoff_sec)
                else:
                    logger.error(f"API Error ({method.__name__}): {msg} (retCode: {code})")

        except Exception as e:
            logger.error(f"API request failed ({method.__name__}): {e}", exc_info=True)

        self.state.consecutive_api_failures += 1
        await self.check_circuit_breaker()
        return None

    async def check_circuit_breaker(self):
        threshold = self.config['risk_management']['circuit_breaker_threshold']
        if self.state.consecutive_api_failures >= threshold:
            if not self.state.is_circuit_breaker_active:
                self.state.is_circuit_breaker_active = True
                logger.critical("[bold red]CIRCUIT BREAKER TRIGGERED[/bold red]")
                await self.cancel_all_orders()
                cooldown = self.config['risk_management']['circuit_breaker_cooldown_seconds']
                logger.warning(f"Trading paused for {cooldown} seconds.")
                await asyncio.sleep(cooldown)
                self.state.consecutive_api_failures = 0
                self.state.is_circuit_breaker_active = False
                logger.info("[bold green]Circuit breaker reset. Resuming.[/bold green]")

    async def fetch_instrument_info(self):
        result = await self._api_call(self.session.get_instruments_info, category='linear', symbol=self.config['symbol'])
        if result and result.get('list'):
            info = result['list'][0]
            self.state.instrument_info = InstrumentInfo(
                tick_size=to_decimal(info['priceFilter']['tickSize'], "0.0001"),
                step_size=to_decimal(info['lotSizeFilter']['qtyStep'], "0.001"),
                min_order_size=to_decimal(info['lotSizeFilter']['minOrderQty'], "0.001")
            )
            ii = self.state.instrument_info
            logger.info(f"Instrument: tick={ii.tick_size}, step={ii.step_size}, min={ii.min_order_size}")
        else:
            logger.error(f"Failed to fetch instrument info for {self.config['symbol']}")

    async def place_and_cancel_orders_batch(self, orders_to_place: list[dict], orders_to_cancel: list[str]):
        if self.config['dry_run']:
            self.virtual_orders.clear()
            for order in orders_to_place:
                order_id = f"dryrun_{uuid.uuid4().hex[:8]}"
                self.virtual_orders[order_id] = order
            if orders_to_place or orders_to_cancel:
                logger.info(f"[DRY RUN] Orders: +{len(orders_to_place)} -{len(orders_to_cancel)}")
            return

        if orders_to_cancel:
            cancel_requests = [{"symbol": self.config['symbol'], "orderId": oid} for oid in orders_to_cancel]
            cancel_result = await self._api_call(self.session.cancel_batch_order, category="linear", request=cancel_requests)
            if cancel_result:
                for oid in orders_to_cancel:
                    self.active_orders.pop(oid, None)

        if orders_to_place:
            place_requests = [
                {
                    "symbol": self.config['symbol'],
                    "side": o['side'],
                    "orderType": "Limit",
                    "qty": str(o['qty']),
                    "price": str(o['price']),
                    "orderLinkId": f"mm_{uuid.uuid4().hex[:8]}",
                    "timeInForce": "PostOnly",
                    "reduceOnly": False
                } for o in orders_to_place
            ]
            place_result = await self._api_call(self.session.place_batch_order, category="linear", request=place_requests)
            if place_result and place_result.get('list'):
                success_count = sum(1 for r in place_result['list'] if r.get('orderId'))
                if success_count > 0:
                    logger.info(f"Placed {success_count}/{len(orders_to_place)} orders")

    async def close_position(self, side: str, qty: Decimal):
        if qty <= 0:
            return

        if self.config['dry_run']:
            if self.state.recent_prices:
                fill_price = self.state.recent_prices[-1]
            elif self.orderbook['bids'] and self.orderbook['asks']:
                best_bid = max(self.orderbook['bids'].keys())
                best_ask = min(self.orderbook['asks'].keys())
                fill_price = best_bid if side == "Sell" else best_ask
            else:
                logger.warning("[DRY RUN] No market data to close position")
                return

            self.position_manager.process_virtual_fill(side, fill_price, qty)
            self.virtual_orders.clear()
            logger.info(f"[DRY RUN] Position closed: {side} {qty} @ {fill_price}")
            return

        formatted_qty = self._format_qty(qty)
        close_result = await self._api_call(
            self.session.place_order,
            category='linear',
            symbol=self.config['symbol'],
            side=side,
            orderType='Market',
            qty=str(formatted_qty),
            reduceOnly=True
        )
        if close_result:
            logger.info(f"Market close order placed: {side} {formatted_qty}")
        else:
            logger.error(f"Failed to close position: {side} {formatted_qty}")

    async def cancel_all_orders(self):
        if self.config['dry_run']:
            if self.virtual_orders:
                logger.info(f"[DRY RUN] Cancelling {len(self.virtual_orders)} orders")
                self.virtual_orders.clear()
            return

        cancel_result = await self._api_call(
            self.session.cancel_all_orders,
            category='linear',
            symbol=self.config['symbol']
        )
        if cancel_result:
            logger.info("All orders cancelled")
            self.active_orders.clear()

    # ------------- WebSocket handling using pybit helper streams -------------
    def _ws_callback(self, message: dict):
        # Marshal into asyncio loop (pybit callback runs in thread)
        try:
            if self.loop:
                asyncio.run_coroutine_threadsafe(self._handle_message(message), self.loop)
        except Exception as e:
            logger.error(f"WS callback dispatch error: {e}", exc_info=True)

    def _start_streams(self):
        """Start pybit-managed websocket subscriptions using helper methods (safe across pybit versions)."""
        symbol = self.config['symbol']
        depth = int(self.config['technical']['orderbook_depth'])

        # Public
        self.ws_public = WebSocket(testnet=self.config['testnet'], channel_type="linear")
        try:
            # Orderbook
            if hasattr(self.ws_public, "orderbook_stream"):
                self.ws_public.orderbook_stream(depth=depth, symbol=symbol, callback=self._ws_callback)
            else:
                # Fallback to subscribe with explicit kwargs if available
                if hasattr(self.ws_public, "subscribe"):
                    self.ws_public.subscribe(topic="orderbook", symbol=[symbol], depth=depth, callback=self._ws_callback)

            # Ticker
            if hasattr(self.ws_public, "ticker_stream"):
                self.ws_public.ticker_stream(symbol=symbol, callback=self._ws_callback)
            else:
                if hasattr(self.ws_public, "subscribe"):
                    self.ws_public.subscribe(topic="tickers", symbol=[symbol], callback=self._ws_callback)

            logger.info("Public WS subscriptions set.")
        except Exception as e:
            logger.critical(f"Failed to start public WS subscriptions: {e}", exc_info=True)
            raise

        # Private (only live)
        self.ws_private = None
        if not self.config['dry_run']:
            try:
                self.ws_private = WebSocket(
                    testnet=self.config['testnet'],
                    channel_type="private",
                    api_key=self.api_key,
                    api_secret=self.api_secret
                )
                # Position
                if hasattr(self.ws_private, "position_stream"):
                    self.ws_private.position_stream(callback=self._ws_callback)
                else:
                    if hasattr(self.ws_private, "subscribe"):
                        self.ws_private.subscribe(topic="position", callback=self._ws_callback)
                # Order
                if hasattr(self.ws_private, "order_stream"):
                    self.ws_private.order_stream(callback=self._ws_callback)
                else:
                    if hasattr(self.ws_private, "subscribe"):
                        self.ws_private.subscribe(topic="order", callback=self._ws_callback)
                # Execution
                if hasattr(self.ws_private, "execution_stream"):
                    self.ws_private.execution_stream(callback=self._ws_callback)
                else:
                    if hasattr(self.ws_private, "subscribe"):
                        self.ws_private.subscribe(topic="execution", callback=self._ws_callback)

                logger.info("Private WS subscriptions set.")
            except Exception as e:
                logger.critical(f"Failed to start private WS subscriptions: {e}", exc_info=True)
                raise

    async def _handle_message(self, msg: dict):
        """Processes incoming messages from pybit WebSocket."""
        topic = msg.get('topic', '')
        data = msg.get('data')

        if topic.startswith("orderbook"):
            book_data = data[0] if isinstance(data, list) else data
            try:
                self.orderbook['bids'] = {to_decimal(p): to_decimal(q) for p, q in book_data.get('b', [])}
                self.orderbook['asks'] = {to_decimal(p): to_decimal(q) for p, q in book_data.get('a', [])}
            except Exception as e:
                logger.error(f"Error parsing orderbook: {e}")

        elif topic.startswith("tickers"):
            if isinstance(data, dict) and data.get('midPrice') is not None:
                mid = to_decimal(data['midPrice'])
                self.state.recent_prices.append(mid)
                self.state.last_mid_price = mid
                if self.config['dry_run']:
                    self.position_manager.refresh_unrealized_pnl(mid)
                # Update TA on each new mid if enabled
                self._update_ta()

        elif not self.config['dry_run']:  # Private topics
            if topic == "position":
                for pos_data in (data if isinstance(data, list) else [data]):
                    if pos_data.get('symbol') == self.config['symbol']:
                        self.position_manager.update_position(pos_data)

            elif topic == "order":
                for order in (data if isinstance(data, list) else [data]):
                    oid = order.get('orderId')
                    status = order.get('orderStatus')
                    if not oid:
                        continue
                    if status in ['New', 'PartiallyFilled']:
                        try:
                            self.active_orders[oid] = {
                                'price': to_decimal(order['price']),
                                'side': order['side'],
                                'qty': to_decimal(order['qty'])
                            }
                        except Exception:
                            pass
                    elif status in ['Filled', 'Cancelled', 'Rejected']:
                        self.active_orders.pop(oid, None)

            elif topic == "execution":
                for trade in (data if isinstance(data, list) else [data]):
                    if trade.get('execType') == 'Trade' and trade.get('symbol') == self.config['symbol']:
                        self.position_manager.process_real_fill(trade)

    # ------------- TA computation -------------
    def _update_ta(self):
        """Compute RSI/EMA/BB from mid-price deque using pandas_ta (if enabled/available)."""
        if not self.ta_enabled:
            return
        try:
            prices = list(self.state.recent_prices)
            if not prices:
                return

            rsi_len = int(self.ta_cfg.get("rsi_length", 14))
            ema_fast = int(self.ta_cfg.get("ema_fast", 12))
            ema_slow = int(self.ta_cfg.get("ema_slow", 26))
            bb_len = int(self.ta_cfg.get("bb_length", 20))
            bb_std = float(self.ta_cfg.get("bb_std", 2.0))

            min_len = max(rsi_len, ema_slow, bb_len) + 2
            if len(prices) < min_len:
                return

            s = pd.Series([float(x) for x in prices], dtype="float64")

            rsi_series = pta.rsi(s, length=rsi_len)
            rsi_val = float(rsi_series.iloc[-1]) if rsi_series is not None and not pd.isna(rsi_series.iloc[-1]) else None

            ema_f_series = pta.ema(s, length=ema_fast)
            ema_s_series = pta.ema(s, length=ema_slow)
            ema_f = float(ema_f_series.iloc[-1]) if ema_f_series is not None and not pd.isna(ema_f_series.iloc[-1]) else None
            ema_s = float(ema_s_series.iloc[-1]) if ema_s_series is not None and not pd.isna(ema_s_series.iloc[-1]) else None

            bb = pta.bbands(s, length=bb_len, std=bb_std)
            bb_width_pct = None
            if bb is not None and not bb.empty:
                upper_col = [c for c in bb.columns if c.startswith("BBU_")]
                lower_col = [c for c in bb.columns if c.startswith("BBL_")]
                mid_col   = [c for c in bb.columns if c.startswith("BBM_")]
                if upper_col and lower_col and mid_col:
                    u, l, m = bb[upper_col[0]].iloc[-1], bb[lower_col[0]].iloc[-1], bb[mid_col[0]].iloc[-1]
                    if m and not any(pd.isna([u, l, m])):
                        bb_width_pct = float((u - l) / m) if m != 0 else None

            self.ta_state["rsi"] = rsi_val
            self.ta_state["ema_fast"] = ema_f
            self.ta_state["ema_slow"] = ema_s
            self.ta_state["bb_width_pct"] = bb_width_pct

        except Exception as e:
            logger.debug(f"TA update failed: {e}")

    # ------------- Strategy -------------
    def _format_price(self, p: Decimal) -> Decimal:
        if not self.state.instrument_info:
            return p
        return round_to_increment(p, self.state.instrument_info.tick_size, ROUND_HALF_UP)

    def _format_qty(self, q: Decimal) -> Decimal:
        if not self.state.instrument_info:
            return q
        q = floor_to_increment(q, self.state.instrument_info.step_size)
        if q < self.state.instrument_info.min_order_size:
            q = self.state.instrument_info.min_order_size
        return q

    def _quotes_significantly_changed(self, current: list, new: list) -> bool:
        if not self.state.instrument_info:
            return True

        if len(current) != len(new):
            return True

        ii = self.state.instrument_info
        price_tol = ii.tick_size * self.price_tol_ticks
        qty_tol = ii.step_size * self.qty_tol_steps if self.qty_tol_steps > 0 else Decimal("0")

        current_sorted = sorted(current, key=lambda x: (x[2], x[0], x[1]))
        new_sorted = sorted(new, key=lambda x: (x[2], x[0], x[1]))

        for (cp, cq, cs), (np, nq, ns) in zip(current_sorted, new_sorted, strict=False):
            if cs != ns:
                return True
            if not approx_equal(cp, np, price_tol):
                return True
            if qty_tol > 0:
                if not approx_equal(cq, nq, qty_tol):
                    return True
            elif cq != nq:
                return True
        return False

    def _calculate_tiered_quotes(self) -> tuple[list[dict], list[dict]]:
        bids = self.orderbook['bids']
        asks = self.orderbook['asks']

        if not bids or not asks:
            return [], []

        best_bid = max(bids.keys())
        best_ask = min(asks.keys())

        if best_bid >= best_ask:
            logger.debug("Market crossed, skipping quotes")
            return [], []

        mid_price = (best_bid + best_ask) / Decimal("2")

        # Volatility (float domain)
        volatility = Decimal("0")
        vol_window = self.config['technical'].get('vol_window', 60)
        if len(self.state.recent_prices) >= vol_window:
            try:
                prices_f = [float(p) for p in list(self.state.recent_prices)[-vol_window:]]
                if len(set(prices_f)) > 1:
                    vol = statistics.stdev(prices_f) / float(mid_price)
                    volatility = Decimal(str(vol))
            except Exception as e:
                logger.debug(f"Volatility calc error: {e}")

        # Dynamic spread (base + vol component)
        base_spread = Decimal(str(self.config['strategy']['base_spread_percentage']))
        vol_mult = Decimal(str(self.config['strategy']['volatility_spread_multiplier']))
        total_spread_pct = base_spread + (volatility * vol_mult)

        # ---- TA-driven adjustments ----
        rsi = self.ta_state["rsi"] if self.ta_enabled else None
        ema_f = self.ta_state["ema_fast"] if self.ta_enabled else None
        ema_s = self.ta_state["ema_slow"] if self.ta_enabled else None
        bbw = self.ta_state["bb_width_pct"] if self.ta_enabled else None

        # RSI-based signal in [-1, 1]
        signal = Decimal("0")
        if rsi is not None:
            signal = clamp_decimal(Decimal((rsi - 50.0) / 50.0), Decimal("-1"), Decimal("1"))

        # Fair value shift by RSI signal (bps)
        fv_bps = Decimal(str(self.ta_cfg.get("signal_fair_value_bps", 2.0)))
        fair_value = mid_price * (Decimal("1") + signal * fv_bps / Decimal("10000"))

        # Spread widening by BB width (% of mid)
        if bbw is not None:
            try:
                bbw_dec = Decimal(str(bbw))
                total_spread_pct += bbw_dec * Decimal(str(self.ta_cfg.get("bb_spread_mult", 0.5)))
            except Exception:
                pass

        # Inventory skew
        max_pos_size = Decimal(str(self.config['risk_management']['max_position_size']))
        skew_intensity = Decimal(str(self.config['strategy']['inventory_skew_intensity']))

        if max_pos_size > 0:
            ratio = self.position_manager.size / max_pos_size
            inv_skew = clamp_decimal(ratio, Decimal("-1"), Decimal("1"))
        else:
            inv_skew = Decimal("0")

        # Apply inventory skew (push fair value away from current inventory)
        fair_value = fair_value * (Decimal("1") - inv_skew * skew_intensity)

        # Order params
        base_size = Decimal(str(self.config['order_management']['base_order_size']))
        tiers = int(self.config['order_management']['order_tiers'])
        tier_spread_bps = Decimal(str(self.config['order_management']['tier_spread_increase_bps']))
        tier_qty_mult = Decimal(str(self.config['order_management']['tier_qty_multiplier']))

        # Include resting orders
        open_orders = self.virtual_orders if self.config['dry_run'] else self.active_orders
        open_buy_qty = sum(o['qty'] for o in open_orders.values() if o['side'] == 'Buy')
        open_sell_qty = sum(o['qty'] for o in open_orders.values() if o['side'] == 'Sell')

        # TA quantity bias: tilt sizes in trend direction (EMA trend or RSI signal)
        qty_bias_max = Decimal(str(self.ta_cfg.get("qty_bias_max", 0.5)))
        trend_up = (ema_f is not None and ema_s is not None and ema_f > ema_s) or (rsi is not None and rsi > 55)
        trend_down = (ema_f is not None and ema_s is not None and ema_f < ema_s) or (rsi is not None and rsi < 45)

        # Map to signal magnitude in [0,1]
        signal_abs = abs(signal)
        buy_bias = Decimal("1")
        sell_bias = Decimal("1")
        if trend_up:
            buy_bias = Decimal("1") + qty_bias_max * signal_abs
        elif trend_down:
            sell_bias = Decimal("1") + qty_bias_max * signal_abs

        buy_orders, sell_orders = [], []

        for i in range(tiers):
            tier_adj = (Decimal(i) * tier_spread_bps) / Decimal("10000")
            bid_price = self._format_price(fair_value * (Decimal("1") - total_spread_pct - tier_adj))
            ask_price = self._format_price(fair_value * (Decimal("1") + total_spread_pct + tier_adj))

            qty_raw = base_size * (Decimal("1") + Decimal(i) * tier_qty_mult)
            qty_buy = self._format_qty(qty_raw * buy_bias)
            qty_sell = self._format_qty(qty_raw * sell_bias)

            potential_long = self.position_manager.size + open_buy_qty + qty_buy
            potential_short = self.position_manager.size - open_sell_qty - qty_sell

            if potential_long <= max_pos_size:
                buy_orders.append({'price': bid_price, 'qty': qty_buy, 'side': 'Buy'})
            if potential_short >= -max_pos_size:
                sell_orders.append({'price': ask_price, 'qty': qty_sell, 'side': 'Sell'})

        return buy_orders, sell_orders

    async def _simulate_fills(self):
        if not self.virtual_orders or not self.orderbook['bids'] or not self.orderbook['asks']:
            return

        best_bid = max(self.orderbook['bids'].keys())
        best_ask = min(self.orderbook['asks'].keys())

        filled_order_ids = []
        for order_id, order in list(self.virtual_orders.items()):
            if order['side'] == 'Buy' and order['price'] >= best_ask:
                self.position_manager.process_virtual_fill('Buy', best_ask, order['qty'])
                filled_order_ids.append(order_id)
            elif order['side'] == 'Sell' and order['price'] <= best_bid:
                self.position_manager.process_virtual_fill('Sell', best_bid, order['qty'])
                filled_order_ids.append(order_id)

        for order_id in filled_order_ids:
            del self.virtual_orders[order_id]

    # ------------- UI -------------
    def generate_status_table(self) -> Table:
        title = f"Bybit Market Maker - {self.config['symbol']} ({datetime.now().strftime('%H:%M:%S')})"
        if self.config['dry_run']:
            title += " [bold yellow](DRY RUN)[/bold yellow]"

        table = Table(title=title, style="cyan", title_justify="left")
        table.add_column("Metric", style="bold magenta", min_width=20)
        table.add_column("Value", min_width=30)

        status = "[bold red]CIRCUIT BREAKER[/bold red]" if self.state.is_circuit_breaker_active else "[bold green]Active[/bold green]"
        table.add_row("Status", status)

        if self.orderbook['bids'] and self.orderbook['asks']:
            best_bid = max(self.orderbook['bids'].keys())
            best_ask = min(self.orderbook['asks'].keys())
            spread = best_ask - best_bid
            spread_bps = (spread / best_bid * 10000) if isinstance(best_bid, Decimal) and best_bid > 0 else 0
            table.add_row("Best Bid/Ask", f"{best_bid:.6f} / {best_ask:.6f}")
            table.add_row("Spread", f"{spread:.6f} ({spread_bps:.1f} bps)")
        else:
            table.add_row("Best Bid/Ask", "No data")
            table.add_row("Spread", "No data")

        pos_color = "green" if self.position_manager.size > 0 else "red" if self.position_manager.size < 0 else "white"
        table.add_row("Position", f"[{pos_color}]{self.position_manager.size}[/{pos_color}]")
        table.add_row("Avg Entry", f"{self.position_manager.avg_entry_price:.6f}")

        unreal_color = "green" if self.position_manager.unrealized_pnl >= 0 else "red"
        real_color = "green" if self.position_manager.realized_pnl >= 0 else "red"
        table.add_row("Unrealized PnL", f"[{unreal_color}]{self.position_manager.unrealized_pnl:.4f}[/{unreal_color}]")
        table.add_row("Realized PnL", f"[{real_color}]{self.position_manager.realized_pnl:.4f}[/{real_color}]")

        open_orders = self.virtual_orders if self.config['dry_run'] else self.active_orders
        buys = len([o for o in open_orders.values() if o['side'] == 'Buy'])
        sells = len([o for o in open_orders.values() if o['side'] == 'Sell'])
        table.add_row("Open Orders", f"{buys} buys / {sells} sells")

        # TA readout
        if self.ta_cfg.get("enabled"):
            if not PANDAS_TA_AVAILABLE:
                table.add_row("TA", "pandas/pandas_ta not installed")
            else:
                rsi = self.ta_state["rsi"]
                ema_f = self.ta_state["ema_fast"]
                ema_s = self.ta_state["ema_slow"]
                bbw = self.ta_state["bb_width_pct"]
                rsi_txt = f"{rsi:.1f}" if isinstance(rsi, float) else "N/A"
                trend = "Up" if (isinstance(ema_f, float) and isinstance(ema_s, float) and ema_f > ema_s) else \
                        "Down" if (isinstance(ema_f, float) and isinstance(ema_s, float) and ema_f < ema_s) else "N/A"
                bbw_txt = f"{bbw*100:.2f}%" if isinstance(bbw, float) else "N/A"
                table.add_row("RSI", rsi_txt)
                table.add_row("EMA Trend", trend)
                table.add_row("BB Width", bbw_txt)

        if len(self.state.recent_prices) >= 30:
            try:
                prices_f = [float(p) for p in list(self.state.recent_prices)[-60:]]
                if len(set(prices_f)) > 1:
                    vol = statistics.stdev(prices_f) / statistics.mean(prices_f)
                    table.add_row("Volatility (1m)", f"{vol:.4%}")
                else:
                    table.add_row("Volatility (1m)", "0.00%")
            except:
                table.add_row("Volatility (1m)", "N/A")

        return table

    # ------------- Main loop -------------
    async def run(self):
        mode = "[bold yellow]DRY RUN[/bold yellow]" if self.config['dry_run'] else "[bold green]LIVE[/bold green]"
        env = "Testnet" if self.config['testnet'] else "Mainnet"
        logger.info(f"Starting bot: {self.config['symbol']} on {env} in {mode} mode")

        # Keep a reference to the current loop for callback dispatching
        self.loop = asyncio.get_running_loop()

        # Initialize instrument and clean slate
        await self.fetch_instrument_info()
        if not self.state.instrument_info:
            raise RuntimeError("Failed to fetch instrument info")
        await self.cancel_all_orders()

        # Start pybit-managed WebSocket subscriptions
        self._start_streams()

        # Warm up for initial data
        logger.info("Waiting for market data...")
        await asyncio.sleep(3)

        with Live(self.generate_status_table(), screen=True, refresh_per_second=2) as live:
            while True:
                try:
                    live.update(self.generate_status_table())

                    if self.state.is_circuit_breaker_active:
                        await asyncio.sleep(1)
                        continue

                    if await self.position_manager.check_and_manage_risk(self.state):
                        await self.cancel_all_orders()
                        logger.info("Position closed by risk manager, pausing 30s")
                        await asyncio.sleep(30)
                        continue

                    if self.config['dry_run']:
                        await self._simulate_fills()

                    now = time.time()
                    if now - self.last_reprice_time < self.config['order_management']['order_reprice_delay_seconds']:
                        await asyncio.sleep(0.1)
                        continue

                    buy_orders, sell_orders = self._calculate_tiered_quotes()
                    open_orders = self.virtual_orders if self.config['dry_run'] else self.active_orders

                    if not buy_orders and not sell_orders:
                        if open_orders:
                            logger.info("No quotes generated, cancelling orders")
                            await self.cancel_all_orders()
                        await asyncio.sleep(0.5)
                        continue

                    current_quotes = [(o['price'], o['qty'], o['side']) for o in open_orders.values()]
                    new_quotes = [(o['price'], o['qty'], o['side']) for o in (buy_orders + sell_orders)]

                    if self._quotes_significantly_changed(current_quotes, new_quotes):
                        await self.place_and_cancel_orders_batch(buy_orders + sell_orders, list(open_orders.keys()))
                        self.last_reprice_time = now

                    await asyncio.sleep(0.1)

                except asyncio.CancelledError:
                    logger.info("Main loop cancelled")
                    break
                except Exception as e:
                    logger.error(f"Main loop error: {e}", exc_info=True)
                    await asyncio.sleep(5)

        # Graceful shutdown of pybit websockets
        try:
            if self.ws_public and hasattr(self.ws_public, "exit"):
                self.ws_public.exit()
            if self.ws_private and hasattr(self.ws_private, "exit"):
                self.ws_private.exit()
        except Exception:
            pass


# =========================
# Entry point
# =========================
async def main():
    """Main entry point."""
    try:
        config_path = Path(__file__).parent / 'config.json'
        with open(config_path, 'rb') as f:
            config = json.loads(f.read())
    except FileNotFoundError:
        logger.critical(f"config.json not found at {config_path}")
        return
    except json.JSONDecodeError as e:
        logger.critical(f"Error parsing config.json: {e}")
        return

    bot = EnhancedBybitMarketMaker(config)
    loop = asyncio.get_running_loop()
    main_task = asyncio.create_task(bot.run())

    def shutdown():
        logger.info("Shutdown signal received")
        main_task.cancel()

    if hasattr(signal, 'SIGINT'):
        try:
            loop.add_signal_handler(signal.SIGINT, shutdown)
            loop.add_signal_handler(signal.SIGTERM, shutdown)
        except NotImplementedError:
            pass  # Windows/limited envs

    try:
        await main_task
    except asyncio.CancelledError:
        logger.info("Bot stopped by user")
    finally:
        await bot.cancel_all_orders()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
