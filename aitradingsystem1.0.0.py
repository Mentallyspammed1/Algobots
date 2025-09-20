# Enhanced and Optimized AI Trading System with Bybit Integration and Robust Risk/Execution Management
# Compatible with Termux and production environments

import asyncio
import json
import logging
import os
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Tuple

import numpy as np
import pandas as pd
import pandas_ta as ta
import google.generativeai as genai

# --- Bybit Integration Dependencies ---
try:
    from pybit.unified_trading import HTTP
    BYBIT_INTEGRATION_ENABLED = True
except ImportError:
    logging.warning("Pybit library not found. Bybit integration disabled. Install with: pip install pybit")
    BYBIT_INTEGRATION_ENABLED = False

# --- Configuration ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Retry Configuration ---
@dataclass
class RetryConfig:
    retries: int = 5
    base_delay: float = 0.5
    max_delay: float = 8.0
    jitter: float = 0.25

# --- Order State Machine ---
class OrderStatus(Enum):
    NEW = "NEW"
    PENDING_CREATE = "PENDING_CREATE"
    ORDER_PLACED = "ORDER_PLACED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    PENDING_CANCEL = "PENDING_CANCEL"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"

@dataclass
class Order:
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    qty: float
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    status: OrderStatus = OrderStatus.NEW
    bybit_order_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    estimated_cost: float = 0.0
    token_usage: Dict[str, int] = field(default_factory=dict)

    def to_dict(self):
        return {
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "qty": self.qty,
            "price": self.price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "status": self.status.value,
            "bybit_order_id": self.bybit_order_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "estimated_cost": self.estimated_cost,
            "token_usage": self.token_usage
        }

# --- Bybit Adapter ---
class BybitAdapter:
    def __init__(self, api_key: str, api_secret: str, retry_cfg: RetryConfig = RetryConfig()):
        if not BYBIT_INTEGRATION_ENABLED:
            raise RuntimeError("Bybit integration not enabled. Please install 'pybit'.")
        if not api_key or not api_secret:
            raise ValueError("Bybit API key and secret required.")
        self.api_key = api_key
        self.api_secret = api_secret
        self.retry_cfg = retry_cfg
        self.session = HTTP(
            api_key=self.api_key,
            api_secret=self.api_secret
        )
        self.orders: Dict[str, Order] = {}
        self.account_info_cache: Optional[Dict[str, Any]] = None
        self.cache_expiry_time: Optional[datetime] = None
        self.CACHE_DURATION = timedelta(seconds=30)

    async def _with_retry(self, fn: Callable, *args, **kwargs):
        delay = self.retry_cfg.base_delay
        for attempt in range(1, self.retry_cfg.retries + 1):
            try:
                return await asyncio.to_thread(fn, *args, **kwargs)
            except Exception as e:
                is_last = attempt == self.retry_cfg.retries
                if is_last or not self._is_retryable(e):
                    logger.exception(f"Fatal Bybit error attempt {attempt}: {e}")
                    raise
                sleep_for = min(delay * (2 ** (attempt - 1)), self.retry_cfg.max_delay) + np.random.rand() * self.retry_cfg.jitter
                logger.warning(f"Retryable Bybit error: {type(e).__name__} attempt={attempt} sleep={sleep_for:.2f}s")
                await asyncio.sleep(sleep_for)

    def _is_retryable(self, e: Exception) -> bool:
        msg = str(e).lower()
        return any(t in msg for t in [
            "timeout", "temporarily", "unavailable", "rate limit", "429",
            "deadline exceeded", "internal server error", "service unavailable", "connection error"
        ])

    def _map_bybit_order_status(self, bybit_status: str) -> OrderStatus:
        status_map = {
            "Created": OrderStatus.ORDER_PLACED,
            "Active": OrderStatus.ORDER_PLACED,
            "PartiallyFilled": OrderStatus.PARTIALLY_FILLED,
            "Filled": OrderStatus.FILLED,
            "Canceled": OrderStatus.CANCELED,
            "PendingCancel": OrderStatus.PENDING_CANCEL,
            "Rejected": OrderStatus.REJECTED,
            "Expired": OrderStatus.EXPIRED,
        }
        return status_map.get(bybit_status, OrderStatus.UNKNOWN)

    def get_historical_klines(self, symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
        logger.info(f"Fetching historical klines for {symbol} ({interval}, limit={limit})")
        try:
            category = "linear" if symbol.endswith("USDT") else "inverse"
            response = self.session.get_kline(category=category, symbol=symbol, interval=interval, limit=limit)
            if response and response['retCode'] == 0 and response['result']['list']:
                data = response['result']['list']
                df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                df.set_index("timestamp", inplace=True)
                df = df.astype(float)
                df.sort_index(inplace=True)
                return df
            else:
                logger.error(f"Failed to fetch klines for {symbol}: {response}")
                return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error fetching klines for {symbol}: {e}")
            return pd.DataFrame()

    def get_real_time_market_data(self, symbol: str, timeframe: str = "1m") -> Dict[str, Any]:
        logger.info(f"Fetching {timeframe} data for {symbol} from Bybit")
        try:
            category = "linear" if symbol.endswith("USDT") else "inverse" if symbol.endswith("USD") else None
            if not category:
                raise ValueError(f"Unsupported symbol format: {symbol}")
            ticker_info = self.session.get_tickers(category=category, symbol=symbol)
            klines_1d = self.session.get_kline(category=category, symbol=symbol, interval="D", limit=1)
            if ticker_info and ticker_info['retCode'] == 0 and ticker_info['result']['list']:
                latest_ticker = ticker_info['result']['list'][0]
                latest_kline_1d = klines_1d['result']['list'][0] if klines_1d and klines_1d['retCode'] == 0 and klines_1d['result']['list'] else None
                return {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "price": float(latest_ticker.get('lastPrice', 0)),
                    "volume_24h": float(latest_kline_1d[5]) if latest_kline_1d else 0,
                    "price_change_24h_pct": float(latest_kline_1d[8]) if latest_kline_1d else 0,
                    "high_24h": float(latest_kline_1d[2]) if latest_kline_1d else 0,
                    "low_24h": float(latest_kline_1d[3]) if latest_kline_1d else 0,
                    "bid": float(latest_ticker.get('bid1Price', 0)),
                    "ask": float(latest_ticker.get('ask1Price', 0)),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "source": "Bybit"
                }
            else:
                logger.error(f"Failed to fetch ticker data for {symbol}: {ticker_info}")
                return {}
        except Exception as e:
            logger.error(f"Error fetching Bybit market data for {symbol}: {e}")
            return {}

    async def _get_cached_account_info(self) -> Dict[str, Any]:
        now = datetime.utcnow()
        if self.account_info_cache and self.cache_expiry_time and now < self.cache_expiry_time:
            logger.debug("Using cached account info.")
            return self.account_info_cache
        logger.debug("Fetching fresh account info from Bybit.")
        account_info = self.get_account_info()
        self.account_info_cache = account_info
        self.cache_expiry_time = now + self.CACHE_DURATION
        return account_info

    def get_account_info(self) -> Dict[str, Any]:
        logger.info("Fetching Bybit account info")
        try:
            wallet_balance_response = self.session.get_wallet_balance(account_type="UNIFIED", coin="USDT")
            positions_response = self.session.get_positions(category="linear", account_type="UNIFIED")
            total_balance = available_balance = 0.0
            if wallet_balance_response and wallet_balance_response['retCode'] == 0 and wallet_balance_response['result']['list']:
                for balance_entry in wallet_balance_response['result']['list']:
                    if balance_entry['coin'] == 'USDT':
                        total_balance = float(balance_entry.get('balance', 0))
                        available_balance = float(balance_entry.get('availableBalance', 0))
                        break
            processed_positions = []
            if positions_response and positions_response['retCode'] == 0 and positions_response['result']['list']:
                for pos in positions_response['result']['list']:
                    if float(pos.get('size', 0)) > 0:
                        processed_positions.append({
                            "symbol": pos.get('symbol'),
                            "size": float(pos.get('size', 0)),
                            "side": "long" if pos.get('side') == 'Buy' else "short",
                            "unrealized_pnl": float(pos.get('unrealisedPnl', 0)),
                            "entry_price": float(pos.get('avgPrice', 0))
                        })
            return {
                "total_balance_usd": total_balance,
                "available_balance": available_balance,
                "positions": processed_positions,
                "margin_ratio": 0.0,
                "risk_level": "moderate"
            }
        except Exception as e:
            logger.error(f"Error fetching Bybit account info: {e}")
            return {}

    def place_order(self, symbol: str, side: str, order_type: str, qty: float, price: Optional[float] = None,
                   stop_loss: Optional[float] = None, take_profit: Optional[float] = None, client_order_id: Optional[str] = None):
        logger.info(f"Placing Bybit order: {symbol} {side} {order_type} {qty} @ {price}")
        if not client_order_id:
            client_order_id = f"AI_{symbol}_{side}_{int(time.time())}_{np.random.randint(1000, 9999)}"
        if order_type in ["Limit", "StopLimit"] and price is None:
            return {"status": "failed", "message": "Price required for Limit/StopLimit orders."}
        if qty <= 0:
            return {"status": "failed", "message": "Quantity must be positive."}
        if side not in ["Buy", "Sell"]:
            return {"status": "failed", "message": "Side must be 'Buy' or 'Sell'."}
        if order_type not in ["Limit", "Market", "StopLimit"]:
            return {"status": "failed", "message": "Unsupported order type."}
        order_params = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),
            "clientOrderId": client_order_id,
        }
        if price is not None:
            order_params["price"] = str(price)
        if stop_loss is not None:
            order_params["stopLoss"] = str(stop_loss)
        if take_profit is not None:
            order_params["takeProfit"] = str(take_profit)
        try:
            response = self.session.create_order(**order_params)
            if response and response['retCode'] == 0:
                order_data = response['result']
                new_order = Order(
                    client_order_id=client_order_id,
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    qty=qty,
                    price=price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    status=OrderStatus.PENDING_CREATE,
                    bybit_order_id=order_data.get('orderId'),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                self.orders[client_order_id] = new_order
                logger.info(f"Order placed: {new_order.client_order_id}, Bybit ID: {new_order.bybit_order_id}")
                return {"status": "success", "order": new_order}
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                logger.error(f"Failed to place Bybit order for {symbol}: {error_msg}")
                if client_order_id in self.orders:
                    self.orders[client_order_id].status = OrderStatus.REJECTED
                    self.orders[client_order_id].updated_at = datetime.utcnow()
                return {"status": "failed", "message": error_msg}
        except Exception as e:
            logger.error(f"Exception during Bybit order placement for {symbol}: {e}")
            if client_order_id in self.orders:
                self.orders[client_order_id].status = OrderStatus.REJECTED
                self.orders[client_order_id].updated_at = datetime.utcnow()
            return {"status": "failed", "message": str(e)}

    def get_order(self, symbol: str, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> Optional[Order]:
        if not order_id and not client_order_id:
            logger.error("order_id or client_order_id required to get order status.")
            return None
        internal_order = self.orders.get(client_order_id) if client_order_id else None
        logger.info(f"Fetching order status for {symbol}, order_id: {order_id}, client_order_id: {client_order_id}")
        try:
            response = self.session.get_order(
                category="linear",
                symbol=symbol,
                orderId=order_id,
                orderLinkId=client_order_id
            )
            if response and response['retCode'] == 0 and response['result']:
                order_data = response['result']
                if internal_order:
                    internal_order.bybit_order_id = order_data.get('orderId', internal_order.bybit_order_id)
                    internal_order.status = self._map_bybit_order_status(order_data.get('orderStatus', internal_order.status.value))
                    internal_order.updated_at = datetime.utcnow()
                    internal_order.price = float(order_data.get('price', internal_order.price)) if order_data.get('price') else internal_order.price
                    internal_order.qty = float(order_data.get('qty', internal_order.qty)) if order_data.get('qty') else internal_order.qty
                    internal_order.stop_loss = float(order_data.get('stopLoss', internal_order.stop_loss)) if order_data.get('stopLoss') else internal_order.stop_loss
                    internal_order.take_profit = float(order_data.get('takeProfit', internal_order.take_profit)) if order_data.get('takeProfit') else internal_order.take_profit
                    logger.info(f"Updated order {internal_order.client_order_id} status to {internal_order.status}")
                    return internal_order
                else:
                    temp_order = Order(
                        client_order_id=order_data.get('orderLinkId'),
                        symbol=order_data.get('symbol'),
                        side=order_data.get('side'),
                        order_type=order_data.get('orderType'),
                        qty=float(order_data.get('qty', 0)),
                        price=float(order_data.get('price', 0)) if order_data.get('price') else None,
                        stop_loss=float(order_data.get('stopLoss', 0)) if order_data.get('stopLoss') else None,
                        take_profit=float(order_data.get('takeProfit', 0)) if order_data.get('takeProfit') else None,
                        status=self._map_bybit_order_status(order_data.get('orderStatus')),
                        bybit_order_id=order_data.get('orderId'),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    self.orders[temp_order.client_order_id] = temp_order
                    logger.info(f"Fetched and cached new order {temp_order.client_order_id} with status {temp_order.status}")
                    return temp_order
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                logger.error(f"Failed to fetch Bybit order {order_id}/{client_order_id}: {error_msg}")
                return None
        except Exception as e:
            logger.error(f"Exception fetching Bybit order {order_id}/{client_order_id}: {e}")
            return None

    def get_open_orders(self, symbol: str) -> List[Order]:
        logger.info(f"Fetching open orders for {symbol} from Bybit")
        open_orders_from_bybit = []
        try:
            response = self.session.get_orders(
                category="linear",
                symbol=symbol,
                orderStatus="Open"
            )
            if response and response['retCode'] == 0 and response['result'] and response['result']['list']:
                for order_data in response['result']['list']:
                    client_order_id = order_data.get('orderLinkId')
                    if client_order_id and client_order_id in self.orders:
                        internal_order = self.orders[client_order_id]
                        internal_order.bybit_order_id = order_data.get('orderId', internal_order.bybit_order_id)
                        internal_order.status = self._map_bybit_order_status(order_data.get('orderStatus', internal_order.status.value))
                        internal_order.updated_at = datetime.utcnow()
                        internal_order.price = float(order_data.get('price', internal_order.price)) if order_data.get('price') else internal_order.price
                        internal_order.qty = float(order_data.get('qty', internal_order.qty)) if order_data.get('qty') else internal_order.qty
                        internal_order.stop_loss = float(order_data.get('stopLoss', internal_order.stop_loss)) if order_data.get('stopLoss') else internal_order.stop_loss
                        internal_order.take_profit = float(order_data.get('takeProfit', internal_order.take_profit)) if order_data.get('takeProfit') else internal_order.take_profit
                        open_orders_from_bybit.append(internal_order)
                    else:
                        temp_order = Order(
                            client_order_id=client_order_id,
                            symbol=order_data.get('symbol'),
                            side=order_data.get('side'),
                            order_type=order_data.get('orderType'),
                            qty=float(order_data.get('qty', 0)),
                            price=float(order_data.get('price', 0)) if order_data.get('price') else None,
                            stop_loss=float(order_data.get('stopLoss', 0)) if order_data.get('stopLoss') else None,
                            take_profit=float(order_data.get('takeProfit', 0)) if order_data.get('takeProfit') else None,
                            status=self._map_bybit_order_status(order_data.get('orderStatus')),
                            bybit_order_id=order_data.get('orderId'),
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        self.orders[temp_order.client_order_id] = temp_order
                        open_orders_from_bybit.append(temp_order)
            return open_orders_from_bybit
        except Exception as e:
            logger.error(f"Exception fetching Bybit open orders for {symbol}: {e}")
            return []

    def cancel_order(self, symbol: str, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> Dict[str, Any]:
        if not order_id and not client_order_id:
            return {"status": "failed", "message": "order_id or client_order_id required for cancellation."}
        internal_order = self.orders.get(client_order_id) if client_order_id else None
        if internal_order and internal_order.status not in [
            OrderStatus.NEW, OrderStatus.PENDING_CREATE, OrderStatus.ORDER_PLACED, OrderStatus.PARTIALLY_FILLED
        ]:
            logger.warning(f"Order {client_order_id} not cancellable: {internal_order.status}")
            return {"status": "failed", "message": f"Order not in cancellable state: {internal_order.status}"}
        if internal_order:
            internal_order.status = OrderStatus.PENDING_CANCEL
            internal_order.updated_at = datetime.utcnow()
        logger.info(f"Cancelling order for {symbol}, order_id: {order_id}, client_order_id: {client_order_id}")
        try:
            response = self.session.cancel_order(
                category="linear",
                symbol=symbol,
                orderId=order_id,
                orderLinkId=client_order_id
            )
            if response and response['retCode'] == 0:
                logger.info(f"Order cancellation request sent for {symbol}, order_id: {order_id}, client_order_id: {client_order_id}")
                return {"status": "success", "message": "Cancellation request sent."}
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                logger.error(f"Failed cancellation for {symbol}, order_id: {order_id}, client_order_id: {client_order_id}: {error_msg}")
                if internal_order:
                    internal_order.status = OrderStatus.REJECTED
                    internal_order.updated_at = datetime.utcnow()
                return {"status": "failed", "message": error_msg}
        except Exception as e:
            logger.error(f"Exception cancelling Bybit order {symbol}: {e}")
            if internal_order:
                internal_order.status = OrderStatus.REJECTED
                internal_order.updated_at = datetime.utcnow()
            return {"status": "failed", "message": str(e)}

# --- Risk Policy ---
class RiskPolicy:
    def __init__(self, bybit_adapter: BybitAdapter, max_risk_per_trade_pct: float = 0.02, max_leverage: float = 10.0):
        self.bybit_adapter = bybit_adapter
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_leverage = max_leverage

    async def _get_account_state(self) -> Dict[str, Any]:
        return await self.bybit_adapter._get_cached_account_info()

    async def validate_trade_proposal(self, symbol: str, side: str, order_type: str, qty: float, price: Optional[float] = None, stop_loss: Optional[float] = None, take_profit: Optional[float] = None):
        account_state = await self._get_account_state()
        total_balance = account_state.get("total_balance_usd", 0)
        available_balance = account_state.get("available_balance", 0)
        if total_balance == 0:
            return False, "No account balance available."
        estimated_entry_price = price
        if estimated_entry_price is None:
            market_data = self.bybit_adapter.get_real_time_market_data(symbol)
            estimated_entry_price = market_data.get("price")
            if estimated_entry_price is None:
                return False, f"Could not fetch price for {symbol}."
        proposed_position_value = qty * estimated_entry_price
        trade_risk_usd = 0
        if stop_loss is not None and estimated_entry_price is not None:
            risk_per_unit = (estimated_entry_price - stop_loss) if side == "Buy" else (stop_loss - estimated_entry_price)
            if risk_per_unit > 0:
                trade_risk_usd = risk_per_unit * qty
            else:
                return False, "Stop loss must be positive risk."
        else:
            return False, "Stop loss required for risk calculation."
        if trade_risk_usd > total_balance * self.max_risk_per_trade_pct:
            return False, f"Trade risk ({trade_risk_usd:.2f}) exceeds max allowed ({total_balance * self.max_risk_per_trade_pct:.2f})."
        if proposed_position_value > available_balance * 5:
            logger.warning(f"Position value ({proposed_position_value:.2f}) high vs available ({available_balance:.2f}).")
        return True, "Trade proposal valid."

# --- Trading Functions ---
class TradingFunctions:
    def __init__(self, bybit_adapter: Optional[BybitAdapter] = None):
        self.bybit_adapter = bybit_adapter
        self.stub_data = {
            "get_real_time_market_data": {
                "symbol": "BTCUSDT", "timeframe": "1m", "price": 45000.50, "volume_24h": 2_500_000_000,
                "price_change_24h_pct": 2.5, "high_24h": 46000.0, "low_24h": 44000.0,
                "bid": 44999.50, "ask": 45001.00, "timestamp": datetime.utcnow().isoformat() + "Z", "source": "stub"
            },
            "calculate_advanced_indicators": {
                "rsi": 65.2, "macd_line": 125.5, "macd_signal": 120.0, "macd_histogram": 5.5,
                "bollinger_upper": 46500.0, "bollinger_middle": 45000.0, "bollinger_lower": 43500.0,
                "volume_sma": 1_800_000.0, "atr": 850.5, "stochastic_k": 72.3, "stochastic_d": 68.9
            },
            "get_portfolio_status": {
                "account_id": "stub_account", "total_balance_usd": 50_000.00, "available_balance": 25_000.00,
                "positions": [{"symbol": "BTCUSDT", "size": 0.5, "side": "long", "unrealized_pnl": 1250.00},
                              {"symbol": "ETHUSDT", "size": 2.0, "side": "long", "unrealized_pnl": -150.00}],
                "margin_ratio": 0.15, "risk_level": "moderate", "timestamp": datetime.utcnow().isoformat() + "Z"
            },
            "execute_risk_analysis": {
                "symbol": "BTCUSDT", "position_value": 45000.0, "risk_reward_ratio": 2.5,
                "max_drawdown_risk": 0.02, "volatility_score": 0.65, "correlation_risk": 0.30,
                "recommended_stop_loss": 44100.0, "recommended_take_profit": 47250.0
            }
        }

    def get_real_time_market_data(self, symbol: str, timeframe: str = "1m") -> Dict[str, Any]:
        if self.bybit_adapter:
            return self.bybit_adapter.get_real_time_market_data(symbol, timeframe)
        logger.warning("Bybit adapter not available, using stub get_real_time_market_data.")
        return self.stub_data["get_real_time_market_data"]

    def calculate_advanced_indicators(self, symbol: str, period: int = 14) -> Dict[str, float]:
        logger.info(f"Calculating indicators for {symbol} (period={period})")
        return self.stub_data["calculate_advanced_indicators"]

    def get_portfolio_status(self, account_id: str) -> Dict[str, Any]:
        if self.bybit_adapter:
            return self.bybit_adapter.get_account_info()
        logger.warning("Bybit adapter not available, using stub get_portfolio_status.")
        return self.stub_data["get_portfolio_status"]

    def execute_risk_analysis(self, symbol: str, position_size: float, entry_price: float, stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> Dict[str, Any]:
        logger.info(f"Risk analysis for {symbol}: size={position_size}, entry={entry_price}, SL={stop_loss}, TP={take_profit}")
        position_value = position_size * entry_price if entry_price is not None else 0
        risk_reward_ratio = max_drawdown_risk = volatility_score = correlation_risk = 0
        side = "Buy"  # Default assumption, enhance for AI
        if stop_loss is not None and entry_price is not None and position_value > 0:
            risk_per_unit = entry_price - stop_loss if side == "Buy" else (stop_loss - entry_price)
            if risk_per_unit > 0:
                trade_risk_usd = risk_per_unit * qty
            else:
                return False, "Stop loss must be positive risk."
        else:
            return False, "Stop loss required for risk calculation."
        if trade_risk_usd > total_balance * self.max_risk_per_trade_pct:
            return False, f"Trade risk ({trade_risk_usd:.2f}) exceeds max allowed ({total_balance * self.max_risk_per_trade_pct:.2f})."
        if proposed_position_value > available_balance * 5:
            logger.warning(f"Position value ({proposed_position_value:.2f}) high vs available ({available_balance:.2f}).")
        return True, "Trade proposal valid."

    def place_order(self, symbol: str, side: str, order_type: str, qty: float, price: Optional[float] = None,
                   stop_loss: Optional[float] = None, take_profit: Optional[float] = None, client_order_id: Optional[str] = None):
        if self.bybit_adapter:
            return self.bybit_adapter.place_order(symbol, side, order_type, qty, price, stop_loss, take_profit, client_order_id)
        logger.warning("Bybit adapter not available, cannot place order.")
        return {"status": "failed", "message": "Bybit adapter not initialized."}

    def cancel_order(self, symbol: str, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> Dict[str, Any]:
        if self.bybit_adapter:
            return self.bybit_adapter.cancel_order(symbol, order_id, client_order_id)
        logger.warning("Bybit adapter not available, cannot cancel order.")
        return {"status": "failed", "message": "Bybit adapter not initialized."}

# --- Main Trading AI System Orchestrator ---
class TradingAISystem:
    def __init__(self, api_key: str, model_id: str = "gemini-1.5-flash"):
        self.gemini_api_key = api_key
        genai.configure(api_key=self.gemini_api_key)
        self.model = genai.GenerativeModel(model_id)
        self.model_id = model_id
        self.gemini_cache = None
        self.trading_funcs = None
        self.bybit_adapter = None
        self.risk_policy = None
        self.retry_cfg = RetryConfig()
        self.order_manager: Dict[str, Order] = {}

        if BYBIT_INTEGRATION_ENABLED and BYBIT_API_KEY and BYBIT_API_SECRET:
            try:
                self.bybit_adapter = BybitAdapter(BYBIT_API_KEY, BYBIT_API_SECRET, self.retry_cfg)
                self.trading_funcs = TradingFunctions(self.bybit_adapter)
                self.risk_policy = RiskPolicy(self.bybit_adapter)
                logger.info("Bybit adapter and Risk Policy initialized.")
            except Exception as e:
                logger.error(f"Failed Bybit adapter init: {e}. Using stubs.")
                self.bybit_adapter = None
                self.trading_funcs = TradingFunctions()
                self.risk_policy = None
        else:
            logger.warning("Bybit integration disabled/missing keys. Using stub trading functions.")
            self.trading_funcs = TradingFunctions()

    async def initialize(self):
        if self.bybit_adapter:
            logger.info("Fetching initial Bybit account state...")
            await self.bybit_adapter._get_cached_account_info()

    async def perform_quantitative_analysis(self, symbol: str):
        logger.info(f"Performing quantitative analysis for {symbol}...")
        market_data = self.trading_funcs.get_real_time_market_data(symbol)
        indicators = self.trading_funcs.calculate_advanced_indicators(symbol)
        portfolio_status = self.trading_funcs.get_portfolio_status("UNIFIED") # Assuming 'UNIFIED' account_id

        prompt = f"""
        Analyze the following market data and technical indicators for {symbol}:

        Market Data: {json.dumps(market_data, indent=2)}
        Technical Indicators: {json.dumps(indicators, indent=2)}
        Portfolio Status: {json.dumps(portfolio_status, indent=2)}

        Provide a comprehensive quantitative analysis. Include:
        1. Current market sentiment (bullish, bearish, neutral) based on the data.
        2. Key insights from the technical indicators.
        3. Potential trading opportunities (buy, sell, hold) with reasoning.
        4. Any risk considerations based on the portfolio status.
        """
        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            analysis = response.text
            logger.info(f"Gemini analysis for {symbol}:\n{analysis}")
            return {"analysis": analysis, "market_data": market_data, "indicators": indicators, "portfolio_status": portfolio_status}
        except Exception as e:
            logger.error(f"Failed to get Gemini analysis: {e}")
            return {"analysis": "Failed to generate analysis.", "error": str(e)}

    async def analyze_market_charts(self, chart_path: str, symbol: str):
        logger.info(f"Analyzing market chart {chart_path} for {symbol}...")
        # Placeholder implementation
        await asyncio.sleep(1)
        return {"chart_analysis": "completed"}

    async def execute_ai_trade_suggestion(self, **kwargs):
        logger.info(f"Executing AI trade suggestion with args: {kwargs}")
        # Placeholder implementation
        await asyncio.sleep(1)
        return {"status": "success", "order": {"bybit_order_id": "dummy_id", "client_order_id": "dummy_client_id"}}

# --- Example Usage ---
async def main():
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set. Please set it.")
        return
    if not BYBIT_INTEGRATION_ENABLED:
        logger.error("Pybit not installed. Cannot run Bybit examples.")
        return
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        logger.error("BYBIT_API_KEY or BYBIT_API_SECRET not set. Cannot run Bybit examples.")
        return

    system = TradingAISystem(api_key=GEMINI_API_KEY)
    await system.initialize()

    while True:
        logger.info("--- Starting new trading cycle ---")
        symbol_to_trade = "BTCUSDT"

        # Perform Quantitative Analysis
        logger.info(f"--- Quantitative Analysis for {symbol_to_trade} ---")
        analysis_response = await system.perform_quantitative_analysis(symbol_to_trade)
        logger.info("Quantitative analysis completed.")

        # Optional: Analyze Market Charts (placeholder for now)
        dummy_chart_path = "dummy_chart.png"
        if not os.path.exists(dummy_chart_path):
            try:
                from PIL import Image, ImageDraw
                img = Image.new('RGB', (60, 30), color = (255, 255, 255))
                d = ImageDraw.Draw(img)
                d.text((10,10), "Chart", fill=(0,0,0))
                img.save(dummy_chart_path)
                logger.info(f"Dummy chart image created: {dummy_chart_path}")
            except ImportError:
                logger.warning("Pillow not installed. Skipping chart analysis.")
                dummy_chart_path = None
        if dummy_chart_path and os.path.exists(dummy_chart_path):
            logger.info(f"--- Analyzing Market Chart for {symbol_to_trade} (placeholder) ---")
            chart_analysis = await system.analyze_market_charts(dummy_chart_path, symbol_to_trade)
            logger.info(f"Chart Analysis Result: {json.dumps(chart_analysis, indent=2)}")

        # Simulate Trade Execution (based on AI suggestion)
        logger.info("--- Simulating Trade Execution ---")
        market_data = system.bybit_adapter.get_real_time_market_data(symbol_to_trade)
        current_price = market_data.get("price")

        if current_price:
            logger.info(f"Current price for {symbol_to_trade}: {current_price}")
            # These would ideally come from AI analysis_response
            ai_suggested_side = "Buy"
            ai_suggested_order_type = "Limit"
            ai_suggested_qty = 0.001
            ai_suggested_entry_price = current_price * 0.99
            ai_suggested_stop_loss = ai_suggested_entry_price * 0.98
            ai_suggested_take_profit = ai_suggested_entry_price * 1.05

            logger.info(f"Simulating AI suggestion: {ai_suggested_side} {ai_suggested_order_type} {ai_suggested_qty} @ {ai_suggested_entry_price}")
            trade_execution_result = await system.execute_ai_trade_suggestion(
                symbol=symbol_to_trade,
                side=ai_suggested_side,
                order_type=ai_suggested_order_type,
                qty=ai_suggested_qty,
                price=ai_suggested_entry_price,
                stop_loss=ai_suggested_stop_loss,
                take_profit=ai_suggested_take_profit
            )
            logger.info(f"Trade Execution Result: {json.dumps(trade_execution_result, indent=2)}")

            if trade_execution_result.get("status") == "success":
                order_id_to_check = trade_execution_result["order"]["bybit_order_id"]
                client_id_to_check = trade_execution_result["order"]["client_order_id"]
                logger.info(f"--- Checking status of order {client_id_to_check} ---")
                updated_order = system.bybit_adapter.get_order(symbol_to_trade, order_id=order_id_to_check, client_order_id=client_id_to_check)
                if updated_order:
                    logger.info(f"Updated order status: {updated_order.status}")
                else:
                    logger.warning("Could not retrieve updated order status.")
        else:
            logger.warning(f"Could not fetch price for {symbol_to_trade}. Skipping trade simulation.")

        logger.info("--- Trading cycle completed. Sleeping for 60 seconds ---")
        await asyncio.sleep(60) # Sleep for 60 seconds before next cycle

if __name__ == "__main__":
    asyncio.run(main())