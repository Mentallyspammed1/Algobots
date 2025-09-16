This is an excellent request! Integrating Bybit, enhancing the risk policy, and ensuring robust error handling are key steps towards a production-ready system.Here's the complete, upgraded, and enhanced code incorporating Bybit integration, a risk policy, improved error handling, and structured execution flows. code Pythondownloadcontent_copyexpand_less    # trading_ai_system_bybit.py

# Production-ready setup with error handling and Bybit integration

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
from google import genai
from google.genai import types

# --- Bybit Integration Dependencies ---
# Ensure you have pybit installed: pip install pybit
try:
    from pybit.unified_trading import HTTP
    BYBIT_INTEGRATION_ENABLED = True
except ImportError:
    logging.warning("Pybit library not found. Bybit integration will be disabled. Install with: pip install pybit")
    BYBIT_INTEGRATION_ENABLED = False

# --- Configuration ---
# Load API keys from environment variables for security
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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
    PENDING_CREATE = "PENDING_CREATE" # Waiting for Bybit API to acknowledge creation
    ORDER_PLACED = "ORDER_PLACED"     # Acknowledged by Bybit, awaiting execution
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
    side: str # "Buy" or "Sell"
    order_type: str # "Limit", "Market", "StopLimit"
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
        """Converts Order object to a dictionary for JSON serialization."""
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
            raise RuntimeError("Bybit integration is not enabled. Please install 'pybit'.")
        if not api_key or not api_secret:
            raise ValueError("Bybit API key and secret must be provided.")
        
        self.api_key = api_key
        self.api_secret = api_secret
        self.retry_cfg = retry_cfg
        self.session = HTTP(
            api_key=self.api_key,
            api_secret=self.api_secret,
            connect_timeout=10,
            read_timeout=10
        )
        self.orders: Dict[str, Order] = {} # Stores orders by client_order_id
        self.account_info_cache: Optional[Dict[str, Any]] = None
        self.cache_expiry_time: Optional[datetime] = None
        self.CACHE_DURATION = timedelta(seconds=30) # Cache account info for 30 seconds

    async def _with_retry(self, fn: Callable, *args, **kwargs):
        """Wrapper for retrying Bybit API calls."""
        delay = self.retry_cfg.base_delay
        for attempt in range(1, self.retry_cfg.retries + 1):
            try:
                # Bybit API calls are synchronous, so we use asyncio.to_thread
                return await asyncio.to_thread(fn, *args, **kwargs)
            except Exception as e:
                is_last = attempt == self.retry_cfg.retries
                if is_last or not self._is_retryable(e):
                    logger.exception(f"Bybit Fatal error on attempt {attempt}: {e}")
                    raise
                sleep_for = min(delay * (2 ** (attempt - 1)), self.retry_cfg.max_delay) + np.random.rand() * self.retry_cfg.jitter
                logger.warning(f"Bybit Retryable error: {type(e).__name__}. attempt={attempt} sleep={sleep_for:.2f}s")
                await asyncio.sleep(sleep_for)

    def _is_retryable(self, e: Exception) -> bool:
        """Determines if a Bybit API error is retryable."""
        msg = str(e).lower()
        # Common Bybit API errors that might be transient
        return any(t in msg for t in ["timeout", "temporarily", "unavailable", "rate limit", "429", "deadline exceeded", "internal server error", "service unavailable", "connection error"])

    def _map_bybit_order_status(self, bybit_status: str) -> OrderStatus:
        """Maps Bybit's order status strings to our internal OrderStatus enum."""
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

    def get_real_time_market_data(self, symbol: str, timeframe: str = "1m") -> Dict[str, Any]:
        """Fetch real-time market data from Bybit."""
        logger.info(f"Fetching {timeframe} data for {symbol} from Bybit")
        try:
            # Determine category based on symbol (e.g., USDT perpetuals)
            if symbol.endswith("USDT"):
                category = "linear"
            elif symbol.endswith("USD"):
                category = "inverse"
            else:
                raise ValueError(f"Unsupported symbol format for Bybit: {symbol}")

            # Fetch ticker info for current price, bid/ask
            ticker_info = self._with_retry(
                self.session.get_tickers,
                category=category,
                symbol=symbol
            )
            
            # Fetch kline data for 24h stats (volume, price change, high/low)
            # Use 'D' (Daily) interval for 24h stats
            klines_1d = self._with_retry(
                self.session.get_kline,
                category=category,
                symbol=symbol,
                interval="D",
                limit=1 # Latest day
            )

            if ticker_info and ticker_info['retCode'] == 0 and ticker_info['result']['list']:
                latest_ticker = ticker_info['result']['list'][0]
                latest_kline_1d = klines_1d['result']['list'][0] if klines_1d and klines_1d['retCode'] == 0 and klines_1d['result']['list'] else None

                return {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "price": float(latest_ticker.get('lastPrice', 0)),
                    "volume_24h": float(latest_kline_1d[5]) if latest_kline_1d else 0, # Volume from 1D kline
                    "price_change_24h_pct": float(latest_kline_1d[8]) if latest_kline_1d else 0, # Price change % from 1D kline
                    "high_24h": float(latest_kline_1d[2]) if latest_kline_1d else 0, # High from 1D kline
                    "low_24h": float(latest_kline_1d[3]) if latest_kline_1d else 0, # Low from 1D kline
                    "bid": float(latest_ticker.get('bid1Price', 0)),
                    "ask": float(latest_ticker.get('ask1Price', 0)),
                    "timestamp": datetime.utcnow().isoformat() + "Z", # Use UTC for consistency
                    "source": "Bybit"
                }
            else:
                logger.error(f"Failed to fetch ticker data for {symbol}: {ticker_info}")
                return {}
        except Exception as e:
            logger.error(f"Error fetching Bybit market data for {symbol}: {e}")
            return {}

    async def _get_cached_account_info(self) -> Dict[str, Any]:
        """Fetches account info, using cache if available and valid."""
        now = datetime.utcnow()
        if self.account_info_cache and self.cache_expiry_time and now < self.cache_expiry_time:
            logger.debug("Using cached account info.")
            return self.account_info_cache
        
        logger.debug("Fetching fresh account info from Bybit.")
        account_info = self.get_account_info() # This is synchronous, so it's called directly
        self.account_info_cache = account_info
        self.cache_expiry_time = now + self.CACHE_DURATION
        return account_info

    def get_account_info(self) -> Dict[str, Any]:
        """Fetch account balance and positions from Bybit."""
        logger.info("Fetching Bybit account info")
        try:
            # Fetch wallet balance for derivatives (assuming unified account)
            wallet_balance_response = self._with_retry(
                self.session.get_wallet_balance,
                account_type="UNIFIED",
                coin="USDT" # Assuming USDT as base currency
            )
            
            # Fetch open positions for linear perpetuals
            positions_response = self._with_retry(
                self.session.get_positions,
                category="linear",
                account_type="UNIFIED"
            )

            total_balance = 0.0
            available_balance = 0.0
            if wallet_balance_response and wallet_balance_response['retCode'] == 0 and wallet_balance_response['result']['list']:
                for balance_entry in wallet_balance_response['result']['list']:
                    if balance_entry['coin'] == 'USDT':
                        total_balance = float(balance_entry.get('balance', 0))
                        available_balance = float(balance_entry.get('availableBalance', 0))
                        break

            processed_positions = []
            if positions_response and positions_response['retCode'] == 0 and positions_response['result']['list']:
                for pos in positions_response['result']['list']:
                    if float(pos.get('size', 0)) > 0: # Only include open positions
                        processed_positions.append({
                            "symbol": pos.get('symbol'),
                            "size": float(pos.get('size', 0)),
                            "side": "long" if pos.get('side') == 'Buy' else "short",
                            "unrealized_pnl": float(pos.get('unrealisedPnl', 0)),
                            "entry_price": float(pos.get('avgPrice', 0))
                        })

            # Placeholder for margin_ratio and risk_level - these require complex calculations
            # based on current positions, margin, and Bybit's specific rules.
            return {
                "total_balance_usd": total_balance,
                "available_balance": available_balance,
                "positions": processed_positions,
                "margin_ratio": 0.0, # Placeholder
                "risk_level": "moderate" # Placeholder
            }
        except Exception as e:
            logger.error(f"Error fetching Bybit account info: {e}")
            return {}

    def place_order(self, symbol: str, side: str, order_type: str, qty: float, price: Optional[float] = None, stop_loss: Optional[float] = None, take_profit: Optional[float] = None, client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """Place an order on Bybit."""
        logger.info(f"Attempting to place Bybit order: {symbol} {side} {order_type} {qty} @ {price}")

        if not client_order_id:
            client_order_id = f"AI_{symbol}_{side}_{int(time.time())}_{np.random.randint(1000, 9999)}"

        # Basic validation before API call
        if order_type in ["Limit", "StopLimit"] and price is None:
            return {"status": "failed", "message": "Price is required for Limit and StopLimit orders."}
        if qty <= 0:
            return {"status": "failed", "message": "Quantity must be positive."}
        if side not in ["Buy", "Sell"]:
            return {"status": "failed", "message": "Side must be 'Buy' or 'Sell'."}
        if order_type not in ["Limit", "Market", "StopLimit"]:
            return {"status": "failed", "message": "Unsupported order type."}

        order_params = {
            "category": "linear", # Assuming linear perpetuals for USDT pairs
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
            response = self._with_retry(self.session.create_order, **order_params)
            
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
                    status=OrderStatus.PENDING_CREATE, # Initial state before confirmation
                    bybit_order_id=order_data.get('orderId'),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                self.orders[client_order_id] = new_order
                logger.info(f"Order placement request successful: {new_order.client_order_id}, Bybit ID: {new_order.bybit_order_id}")
                return {"status": "success", "order": new_order}
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                logger.error(f"Failed to place Bybit order for {symbol}: {error_msg}")
                # Update order status to REJECTED if it exists in our cache
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
        """Get order status from Bybit and update internal state."""
        if not order_id and not client_order_id:
            logger.error("Either order_id or client_order_id is required to get order status.")
            return None

        # Try to find the order in our internal cache first
        internal_order = None
        if client_order_id and client_order_id in self.orders:
            internal_order = self.orders[client_order_id]
        elif order_id:
            # If only Bybit order_id is provided, we might not have it in cache.
            # We'll fetch it and create a temporary internal order if not found.
            pass

        logger.info(f"Fetching Bybit order status for symbol: {symbol}, order_id: {order_id}, client_order_id: {client_order_id}")
        try:
            response = self._with_retry(
                self.session.get_order,
                category="linear",
                symbol=symbol,
                orderId=order_id,
                orderLinkId=client_order_id
            )

            if response and response['retCode'] == 0 and response['result']:
                order_data = response['result']
                
                # If we found an internal order, update it.
                if internal_order:
                    internal_order.bybit_order_id = order_data.get('orderId', internal_order.bybit_order_id)
                    internal_order.status = self._map_bybit_order_status(order_data.get('orderStatus', internal_order.status.value))
                    internal_order.updated_at = datetime.utcnow()
                    # Update other fields if they changed
                    internal_order.price = float(order_data.get('price', internal_order.price)) if order_data.get('price') else internal_order.price
                    internal_order.qty = float(order_data.get('qty', internal_order.qty)) if order_data.get('qty') else internal_order.qty
                    internal_order.stop_loss = float(order_data.get('stopLoss', internal_order.stop_loss)) if order_data.get('stopLoss') else internal_order.stop_loss
                    internal_order.take_profit = float(order_data.get('takeProfit', internal_order.take_profit)) if order_data.get('takeProfit') else internal_order.take_profit
                    
                    logger.info(f"Updated order {internal_order.client_order_id} status to {internal_order.status}")
                    return internal_order
                else:
                    # If we didn't have it in cache, create a temporary one
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
                        created_at=datetime.utcnow(), # Placeholder, actual creation time might be in Bybit response
                        updated_at=datetime.utcnow()
                    )
                    self.orders[temp_order.client_order_id] = temp_order # Add to cache
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
        """Get all open orders for a given symbol from Bybit and update internal state."""
        logger.info(f"Fetching all open orders for {symbol} from Bybit")
        open_orders_from_bybit = []
        try:
            response = self._with_retry(
                self.session.get_orders,
                category="linear",
                symbol=symbol,
                orderStatus="Open" # Fetch only open orders
            )
            if response and response['retCode'] == 0 and response['result'] and response['result']['list']:
                for order_data in response['result']['list']:
                    client_order_id = order_data.get('orderLinkId')
                    
                    if client_order_id and client_order_id in self.orders:
                        # Update existing internal order
                        internal_order = self.orders[client_order_id]
                        internal_order.bybit_order_id = order_data.get('orderId', internal_order.bybit_order_id)
                        internal_order.status = self._map_bybit_order_status(order_data.get('orderStatus', internal_order.status.value))
                        internal_order.updated_at = datetime.utcnow()
                        # Update other fields if they changed
                        internal_order.price = float(order_data.get('price', internal_order.price)) if order_data.get('price') else internal_order.price
                        internal_order.qty = float(order_data.get('qty', internal_order.qty)) if order_data.get('qty') else internal_order.qty
                        internal_order.stop_loss = float(order_data.get('stopLoss', internal_order.stop_loss)) if order_data.get('stopLoss') else internal_order.stop_loss
                        internal_order.take_profit = float(order_data.get('takeProfit', internal_order.take_profit)) if order_data.get('takeProfit') else internal_order.take_profit
                        
                        open_orders_from_bybit.append(internal_order)
                    else:
                        # If it's an open order from Bybit but not in our cache, create a temporary one
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
                            created_at=datetime.utcnow(), # Placeholder
                            updated_at=datetime.utcnow()
                        )
                        self.orders[temp_order.client_order_id] = temp_order # Add to cache
                        open_orders_from_bybit.append(temp_order)
            return open_orders_from_bybit
        except Exception as e:
            logger.error(f"Exception fetching Bybit open orders for {symbol}: {e}")
            return []

    def cancel_order(self, symbol: str, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """Cancel an order on Bybit."""
        if not order_id and not client_order_id:
            return {"status": "failed", "message": "Either order_id or client_order_id is required for cancellation."}

        # Find the internal order to update its status proactively
        internal_order = None
        if client_order_id and client_order_id in self.orders:
            internal_order = self.orders[client_order_id]
            # Check if the order is in a cancellable state
            if internal_order.status not in [OrderStatus.NEW, OrderStatus.PENDING_CREATE, OrderStatus.ORDER_PLACED, OrderStatus.PARTIALLY_FILLED]:
                logger.warning(f"Order {client_order_id} is not in a cancellable state: {internal_order.status}")
                return {"status": "failed", "message": f"Order not in cancellable state: {internal_order.status}"}
            internal_order.status = OrderStatus.PENDING_CANCEL
            internal_order.updated_at = datetime.utcnow()
        
        logger.info(f"Sending cancellation request for {symbol}, order_id: {order_id}, client_order_id: {client_order_id}")
        try:
            response = self._with_retry(
                self.session.cancel_order,
                category="linear",
                symbol=symbol,
                orderId=order_id,
                orderLinkId=client_order_id
            )

            if response and response['retCode'] == 0:
                logger.info(f"Order cancellation request sent successfully for {symbol}, order_id: {order_id}, client_order_id: {client_order_id}")
                # The actual status update will happen upon the next get_order call.
                return {"status": "success", "message": "Cancellation request sent."}
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                logger.error(f"Failed to send Bybit order cancellation for {symbol}, order_id: {order_id}, client_order_id: {client_order_id}: {error_msg}")
                if internal_order:
                    # If cancellation failed, revert status or mark as failed
                    internal_order.status = OrderStatus.REJECTED # Or keep previous status if cancellation failed
                    internal_order.updated_at = datetime.utcnow()
                return {"status": "failed", "message": error_msg}
        except Exception as e:
            logger.error(f"Exception during Bybit order cancellation for {symbol}: {e}")
            if internal_order:
                internal_order.status = OrderStatus.REJECTED
                internal_order.updated_at = datetime.utcnow()
            return {"status": "failed", "message": str(e)}

# --- Risk Policy ---
class RiskPolicy:
    def __init__(self, bybit_adapter: BybitAdapter, max_risk_per_trade_pct: float = 0.02, max_leverage: float = 10.0):
        self.bybit_adapter = bybit_adapter
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_leverage = max_leverage # This is a general limit, Bybit might have specific limits per symbol/account

    async def _get_account_state(self) -> Dict[str, Any]:
        """Fetches and returns current account state (balance, positions) using cached data."""
        return await self.bybit_adapter._get_cached_account_info()

    async def validate_trade_proposal(self, symbol: str, side: str, order_type: str, qty: float, price: Optional[float] = None, stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> Tuple[bool, str]:
        """
        Validates a proposed trade against risk policies.
        Returns (is_valid, reason_string).
        """
        account_state = await self._get_account_state()
        total_balance = account_state.get("total_balance_usd", 0)
        available_balance = account_state.get("available_balance", 0)

        if total_balance == 0:
            return False, "No account balance available."

        # --- Determine Trade Parameters ---
        estimated_entry_price = price
        if estimated_entry_price is None:
            # If price is not provided (e.g., for Market orders), fetch current price
            market_data = self.bybit_adapter.get_real_time_market_data(symbol)
            estimated_entry_price = market_data.get("price")
            if estimated_entry_price is None:
                return False, f"Could not fetch current price for {symbol} to estimate trade parameters."

        # Calculate proposed position value
        proposed_position_value = qty * estimated_entry_price

        # --- Risk Calculation ---
        trade_risk_usd = 0
        if stop_loss is not None and estimated_entry_price is not None:
            if side == "Buy":
                risk_per_unit = estimated_entry_price - stop_loss
            else: # Sell
                risk_per_unit = stop_loss - estimated_entry_price
            
            if risk_per_unit > 0:
                trade_risk_usd = risk_per_unit * qty
            else:
                return False, "Stop loss must be set such that risk per unit is positive."
        else:
            # If no stop loss is provided, we cannot accurately calculate risk.
            # For AI-generated trades, requiring SL is crucial for risk management.
            return False, "Stop loss is required for risk calculation."

        # --- Policy Checks ---
        # 1. Check risk per trade
        if trade_risk_usd > total_balance * self.max_risk_per_trade_pct:
            return False, f"Trade risk ({trade_risk_usd:.2f} USD) exceeds maximum allowed ({total_balance * self.max_risk_per_trade_pct:.2f} USD)."

        # 2. Check available balance for margin (simplified)
        # This is a rough check. Actual margin requirements depend on leverage and Bybit's rules.
        # A more precise check would involve calculating required margin.
        if proposed_position_value > available_balance * 5: # Arbitrary multiplier, assuming some leverage might be used
             logger.warning(f"Proposed position value ({proposed_position_value:.2f}) is high relative to available balance ({available_balance:.2f}).")
             # This might not be a hard fail if leverage is used, but worth noting.

        # 3. Check leverage (if applicable) - Bybit's API allows setting leverage per order.
        # This check would be more complex, involving current positions and Bybit's max leverage.
        # For now, we rely on the AI to suggest reasonable leverage or Bybit's defaults.

        return True, "Trade proposal is valid."

# --- Trading Functions (incorporating Bybit Adapter) ---
class TradingFunctions:
    def __init__(self, bybit_adapter: Optional[BybitAdapter] = None):
        self.bybit_adapter = bybit_adapter
        # Stub implementations if Bybit adapter is not provided
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
        """Fetch real-time market data."""
        if self.bybit_adapter:
            return self.bybit_adapter.get_real_time_market_data(symbol, timeframe)
        else:
            logger.warning("Bybit adapter not available, using stub data for get_real_time_market_data.")
            return self.stub_data["get_real_time_market_data"]

    def calculate_advanced_indicators(self, symbol: str, period: int = 14) -> Dict[str, float]:
        """Calculate comprehensive technical indicators for analysis."""
        # This is a calculation, not an API call, so it remains as is.
        # In a real system, this would use historical data fetched via get_real_time_market_data
        # or a dedicated historical data API.
        logger.info(f"Calculating technical indicators for {symbol} (period={period})")
        # For demonstration, returning stub data.
        return self.stub_data["calculate_advanced_indicators"]

    def get_portfolio_status(self, account_id: str) -> Dict[str, Any]:
        """Retrieve current portfolio positions and balances."""
        if self.bybit_adapter:
            # Account ID is a placeholder for Gemini's tool definition, not directly used by Bybit adapter here.
            return self.bybit_adapter.get_account_info()
        else:
            logger.warning("Bybit adapter not available, using stub data for get_portfolio_status.")
            return self.stub_data["get_portfolio_status"]

    def execute_risk_analysis(self, symbol: str, position_size: float, entry_price: float, stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> Dict[str, Any]:
        """Perform comprehensive risk analysis for a potential trade."""
        # This function is primarily for analysis and suggestion.
        # The actual validation happens in the RiskPolicy before execution.
        logger.info(f"Performing risk analysis for {symbol}: size={position_size}, entry={entry_price}, SL={stop_loss}, TP={take_profit}")
        
        # Placeholder for actual calculation logic if not using AI for this part.
        # For now, we can return a structured suggestion based on inputs.
        # In a real scenario, this might call a dedicated risk calculation engine.
        
        # Simple calculation of position value
        position_value = position_size * entry_price if entry_price is not None else 0

        # Placeholder for other risk metrics
        risk_reward_ratio = 0
        max_drawdown_risk = 0
        volatility_score = 0
        correlation_risk = 0

        if stop_loss is not None and entry_price is not None and position_value > 0:
            if side == "Buy":
                risk_per_unit = entry_price - stop_loss
            else: # Sell
                risk_per_unit = stop_loss - entry_price
            
            if risk_per_unit > 0:
                trade_risk_usd = risk_per_unit * position_size
                # Assuming total balance is available for risk-reward ratio calculation
                # This would ideally come from get_portfolio_status
                total_balance_usd = 50000.0 # Stub value
                risk_reward_ratio = (take_profit - entry_price) / risk_per_unit if take_profit is not None and side == "Buy" else (entry_price - take_profit) / risk_per_unit if take_profit is not None and side == "Sell" else 0
                max_drawdown_risk = trade_risk_usd / total_balance_usd if total_balance_usd > 0 else 0
        
        return {
            "symbol": symbol,
            "position_value": position_value,
            "risk_reward_ratio": round(risk_reward_ratio, 2) if risk_reward_ratio else None,
            "max_drawdown_risk": round(max_drawdown_risk, 2) if max_drawdown_risk else None,
            "volatility_score": volatility_score,
            "correlation_risk": correlation_risk,
            "recommended_stop_loss": stop_loss,
            "recommended_take_profit": take_profit
        }

    # --- Order Execution Functions (for AI to call directly if enabled) ---
    # These would need careful sandboxing and human oversight.
    # For now, they are defined but not exposed to Gemini by default for safety.
    def place_order(self, symbol: str, side: str, order_type: str, qty: float, price: Optional[float] = None, stop_loss: Optional[float] = None, take_profit: Optional[float] = None, client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """Place an order on the exchange."""
        if self.bybit_adapter:
            return self.bybit_adapter.place_order(symbol, side, order_type, qty, price, stop_loss, take_profit, client_order_id)
        else:
            logger.warning("Bybit adapter not available, cannot place order.")
            return {"status": "failed", "message": "Bybit adapter not initialized."}

    def cancel_order(self, symbol: str, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """Cancel an existing order."""
        if self.bybit_adapter:
            return self.bybit_adapter.cancel_order(symbol, order_id, client_order_id)
        else:
            logger.warning("Bybit adapter not available, cannot cancel order.")
            return {"status": "failed", "message": "Bybit adapter not initialized."}

# --- Main Trading AI System Orchestrator ---
class TradingAISystem:
    def __init__(self, api_key: str, model_id: str = "gemini-2.5-flash"):
        self.gemini_api_key = api_key
        self.gemini_client = genai.Client(api_key=self.gemini_api_key)
        self.model_id = model_id
        self.gemini_cache = None
        self.trading_funcs = None
        self.bybit_adapter = None
        self.risk_policy = None
        self.retry_cfg = RetryConfig()
        self.order_manager: Dict[str, Order] = {} # Stores Order objects by client_order_id

        # Initialize Bybit adapter if keys are available
        if BYBIT_INTEGRATION_ENABLED and BYBIT_API_KEY and BYBIT_API_SECRET:
            try:
                self.bybit_adapter = BybitAdapter(BYBIT_API_KEY, BYBIT_API_SECRET, self.retry_cfg)
                self.trading_funcs = TradingFunctions(self.bybit_adapter)
                self.risk_policy = RiskPolicy(self.bybit_adapter)
                logger.info("Bybit adapter and Risk Policy initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize Bybit adapter: {e}. Trading functionalities will use stubs.")
                self.bybit_adapter = None
                self.trading_funcs = TradingFunctions() # Fallback to stub functions
                self.risk_policy = None
        else:
            logger.warning("Bybit integration is disabled or API keys are missing. Trading functionalities will use stubs.")
            self.trading_funcs = TradingFunctions() # Use stub functions

    async def initialize(self):
        """Initialize the trading system with cached context and Bybit adapter."""
        await self._setup_trading_context_cache()
        # Optionally, fetch initial account state here if Bybit is enabled
        if self.bybit_adapter:
            logger.info("Fetching initial account state for Bybit...")
            await self.bybit_adapter._get_cached_account_info() # Populates cache

    async def _setup_trading_context_cache(self):
        """Create optimized cache for large market context data for Gemini."""
        market_context = """
        COMPREHENSIVE MARKET ANALYSIS FRAMEWORK

        === TECHNICAL ANALYSIS RULES ===
        RSI Interpretation:
        - RSI > 70: Overbought condition, consider selling
        - RSI < 30: Oversold condition, consider buying
        - RSI 40-60: Neutral zone, look for other confirmations

        MACD Analysis:
        - MACD line above signal: Bullish momentum
        - MACD line below signal: Bearish momentum
        - Histogram increasing: Strengthening trend

        === RISK MANAGEMENT PROTOCOLS ===
        Position Sizing Rules:
        - Never risk more than 2% of portfolio per trade
        - Use Kelly Criterion for optimal position sizing
        - Adjust size based on volatility (ATR-based)

        === MARKET REGIME CLASSIFICATION ===
        Bull Market Indicators:
        - Price above 200-day SMA
        - Higher highs and higher lows
        - Increasing volume on up moves

        Bear Market Indicators:
        - Price below 200-day SMA
        - Lower highs and lower lows
        - Increasing volume on down moves

        === CORRELATION ANALYSIS ===
        Asset Correlations:
        - BTC-ETH correlation typically 0.7-0.9
        - During market stress, correlations approach 1.0
        - Consider correlation when building portfolio
        """
        try:
            self.gemini_cache = self.gemini_client.caches.create(
                model=self.model_id,
                config=types.CreateCachedContentConfig(
                    contents=[{"role": "user", "parts": [{"text": market_context}]}],
                    system_instruction="You are a professional quantitative trading analyst.",
                    ttl="7200s"  # 2 hours cache duration
                )
            )
            logger.info(f"Created Gemini market context cache: {self.gemini_cache.name}")
            logger.info(f"Cache token count: {self.gemini_cache.usage_metadata.total_token_count}")
        except Exception as e:
            logger.error(f"Failed to create Gemini cache: {e}")
            self.gemini_cache = None

    def _create_function_declaration(self, name: str, description: str, params: Dict[str, Any]):
        """Helper to create Gemini FunctionDeclaration objects."""
        return types.FunctionDeclaration(
            name=name,
            description=description,
            parameters=types.Schema(
                type="object",
                properties=params,
                required=[k for k, v in params.items() if v.get("required")]
            )
        )

    def _get_trading_function_declarations(self) -> List[types.FunctionDeclaration]:
        """Returns a list of function declarations for Gemini."""
        # These declarations are used for Gemini's function calling mechanism.
        # They describe the available tools/functions to the model.
        declarations = [
            self._create_function_declaration(
                "get_real_time_market_data", "Fetch real-time OHLCV and L2 fields.",
                {
                    "symbol": {"type": "string", "description": "Ticker symbol (e.g., BTCUSDT)", "required": True},
                    "timeframe": {"type": "string", "description": "Candle timeframe (e.g., 1m, 1h, 1D)", "required": False}
                }
            ),
            self._create_function_declaration(
                "calculate_advanced_indicators", "Compute technical indicators like RSI, MACD, Bollinger Bands, etc.",
                {"symbol": {"type": "string", "required": True}, "period": {"type": "integer", "required": False}}
            ),
            self._create_function_declaration(
                "get_portfolio_status", "Retrieve current portfolio balances, positions, and risk levels.",
                {"account_id": {"type": "string", "required": True, "description": "Identifier for the trading account (e.g., 'main_account')."}}
            ),
            self._create_function_declaration(
                "execute_risk_analysis", "Perform pre-trade risk analysis for a proposed trade.",
                {
                    "symbol": {"type": "string", "required": True},
                    "position_size": {"type": "number", "required": True, "description": "The quantity of the asset to trade."},
                    "entry_price": {"type": "number", "required": True, "description": "The desired entry price for the trade."},
                    "stop_loss": {"type": "number", "required": False, "description": "The price level for the stop-loss order."},
                    "take_profit": {"type": "number", "required": False, "description": "The price level for the take-profit order."}
                }
            ),
        ]
        
        # Conditionally add order execution functions if Bybit adapter is available and AI is trusted to call them.
        # WARNING: Directly exposing order placement to AI requires extreme caution, sandboxing, and human oversight.
        # For this example, we'll keep them commented out by default.
        # if self.bybit_adapter:
        #     declarations.extend([
        #         self._create_function_declaration(
        #             "place_order", "Place a trade order on the exchange.",
        #             {
        #                 "symbol": {"type": "string", "required": True},
        #                 "side": {"type": "string", "required": True, "enum": ["Buy", "Sell"]},
        #                 "order_type": {"type": "string", "required": True, "enum": ["Limit", "Market", "StopLimit"]},
        #                 "qty": {"type": "number", "required": True},
        #                 "price": {"type": "number", "required": False, "description": "Required for Limit and StopLimit orders."},
        #                 "stop_loss": {"type": "number", "required": False, "description": "Stop loss price."},
        #                 "take_profit": {"type": "number", "required": False, "description": "Take profit price."}
        #             }
        #         ),
        #         self._create_function_declaration(
        #             "cancel_order", "Cancel an existing order.",
        #             {
        #                 "symbol": {"type": "string", "required": True},
        #                 "order_id": {"type": "string", "required": False, "description": "The Bybit order ID."},
        #                 "client_order_id": {"type": "string", "required": False, "description": "The unique client-generated order ID."}
        #             }
        #         )
        #     ])
        return declarations

    async def create_advanced_trading_session(self):
        """Create a sophisticated trading analysis session with full tool integration."""
        system_instruction = """You are an expert quantitative trading analyst with deep knowledge of:
        - Technical analysis and chart patterns
        - Risk management and portfolio optimization
        - Market microstructure and order flow analysis
        - Macroeconomic factors affecting crypto markets
        - Statistical arbitrage and algorithmic trading strategies

        Use the available tools to gather data, perform calculations, and provide
        actionable trading insights. Always consider risk management in your recommendations.
        Provide specific entry/exit points, position sizing, and risk parameters.
        If suggesting a trade, also provide the stop loss and take profit levels."""

        # Use bound Python tools for chat sessions for simpler integration
        tools = [
            self.trading_funcs.get_real_time_market_data,
            self.trading_funcs.calculate_advanced_indicators,
            self.trading_funcs.get_portfolio_status,
            self.trading_funcs.execute_risk_analysis
        ]

        chat = self.gemini_client.chats.create(
            model=self.model_id,
            config=types.ChatConfig(
                system_instruction=system_instruction,
                tools=tools,
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode="auto")
                ),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    maximum_remote_calls=10 # Allow multiple tool calls per response
                ),
                cached_content=self.gemini_cache.name if self.gemini_cache else None
            )
        )
        return chat

    async def analyze_market_charts(self, chart_image_path: str, symbol: str) -> Dict[str, Any]:
        """Analyze trading charts using Gemini's vision capabilities."""
        if not os.path.exists(chart_image_path):
            return {"error": f"Image file not found at {chart_image_path}"}

        try:
            uploaded_file = self.gemini_client.files.upload(path=chart_image_path)
            prompt = f"""
            Analyze the {symbol} chart image. Return JSON with:
            - pattern: key chart pattern(s) if any
            - momentum_view: bull/bear/neutral with 1-2 sentence rationale
            - sr_levels: up to 5 support/resistance price levels as floats
            - risks: up to 3 notable risks
            - suggested_plan: entry, stop, targets (do NOT recommend >2% risk of equity)
            """
            resp = self.gemini_client.models.generate_content(
                model=self.model_id,
                contents=[
                    {"role": "user", "parts": [{"text": prompt}, {"file_data": {"file_uri": uploaded_file.uri}}]}
                ],
                config=types.GenerateContentConfig(
                    cached_content=self.gemini_cache.name if self.gemini_cache else None,
                    response_mime_type="application/json"
                )
            )
            
            if not resp.candidates or not resp.candidates[0].content.parts:
                return {"error": "No response from model."}

            text = resp.candidates[0].content.parts[0].text
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                logger.warning("Model did not return valid JSON for chart analysis; returning raw text.")
                return {"raw": text}
        except Exception as e:
            logger.error(f"Error analyzing market charts for {symbol}: {e}")
            return {"error": str(e)}

    async def perform_quantitative_analysis(self, symbol: str):
        """Use Gemini's code execution for advanced quantitative analysis."""
        analysis_prompt = f"""
        Perform comprehensive quantitative analysis for {symbol}:

        1. Fetch current market data using get_real_time_market_data(symbol="{symbol}")
        2. Calculate technical indicators using calculate_advanced_indicators(symbol="{symbol}")
        3. Provide a risk-aware trade idea with entry/stop/target and max 2% risk of equity.
        4. If beneficial, emit Python code to:
           - Create price charts with technical overlays
           - Calculate correlation with major market indices
           - Perform Monte Carlo simulation for price projections
           - Generate risk-adjusted return metrics
        Output sections: data_summary, indicators, trade_plan, optional_code.
        """
        try:
            response = self.gemini_client.models.generate_content(
                model=self.model_id,
                contents=analysis_prompt,
                config=types.GenerateContentConfig(
                    cached_content=self.gemini_cache.name if self.gemini_cache else None,
                    tools=[
                        # Use bound Python tools for consistency
                        self.trading_funcs.get_real_time_market_data,
                        self.trading_funcs.calculate_advanced_indicators,
                        self.trading_funcs.get_portfolio_status,
                        self.trading_funcs.execute_risk_analysis,
                        types.Tool(code_execution={}) # Enable code execution
                    ],
                    tool_config=types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(mode="auto")
                    )
                )
            )

            # Process and log generated code blocks
            code_blocks = []
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'executable_code'):
                    code_blocks.append(part.executable_code.code)
                    logger.info(f"Generated code for {symbol} (preview):\n{part.executable_code.code[:1000]}...")
            
            # In a production environment, code execution should be sandboxed.
            # For this example, we just log it.
            # If you want to execute:
            # for code in code_blocks:
            #     try:
            #         # Execute in a safe environment
            #         exec_result = await self.execute_sandboxed_code(code)
            #         logger.info(f"Sandboxed execution result: {exec_result}")
            #     except Exception as e:
            #         logger.error(f"Error executing sandboxed code: {e}")

            return response
        except Exception as e:
            logger.error(f"Error performing quantitative analysis for {symbol}: {e}")
            return {"error": str(e)}

    async def start_live_trading_session(self):
        """Start real-time trading session with Gemini Live API."""
        if not self.gemini_api_key:
            logger.error("Gemini API key not set. Cannot start live session.")
            return
        if not self.bybit_adapter:
            logger.error("Bybit adapter not initialized. Cannot start live session.")
            return

        session_config = types.LiveConnectConfig(
            model=self.model_id,
            config=types.GenerationConfig(response_modalities=["text"]), # Only text for simplicity
            tools=[
                types.Tool(function_declarations=self._get_trading_function_declarations()),
                types.Tool(code_execution={}) # Enable code execution in live session
            ]
        )
        
        try:
            async with self.gemini_client.aio.live.connect(config=session_config) as session:
                async def handle_server_messages():
                    """Process real-time market updates and AI responses from the server."""
                    try:
                        async for response in session.receive():
                            if response.server_content:
                                for part in response.server_content.model_turn.parts:
                                    if hasattr(part, 'text'):
                                        print(f"[AI] {part.text}")
                                    elif hasattr(part, 'code_execution_result'):
                                        print(f"[AI Code Result] {part.code_execution_result.output}")
                                    elif hasattr(part, 'function_call'):
                                        # Handle function calls requested by AI
                                        func_name = part.function_call.name
                                        func_args = dict(part.function_call.args or {})
                                        logger.info(f"AI requested function call: {func_name} with args: {func_args}")
                                        
                                        # Execute the requested function and send result back to server
                                        result_json = await self._execute_tool_call(func_name, func_args)
                                        await session.send(result_json, end_of_turn=True)
                    except Exception as e:
                        logger.error(f"Error in message receive loop: {e}")
                        # Attempt to gracefully close the session if receive fails
                        await session.close()

                async def send_user_queries():
                    """Send continuous user queries to the server."""
                    try:
                        while True:
                            query = await asyncio.to_thread(input, "Query (q=quit): ")
                            if query.strip().lower() == "q":
                                await session.send("Ending session.", end_of_turn=True)
                                break
                            await session.send(query, end_of_turn=True)
                            await asyncio.sleep(0.25) # Small delay to prevent overwhelming
                    except Exception as e:
                        logger.error(f"Error in query send loop: {e}")
                        # Attempt to gracefully close the session if send fails
                        await session.close()

                await asyncio.gather(handle_server_messages(), send_user_queries())
        except Exception as e:
            logger.error(f"Failed to connect to live session or run loops: {e}")

    async def _execute_tool_call(self, func_name: str, func_args: Dict[str, Any]) -> str:
        """
        Executes a tool call requested by the AI.
        Validates arguments, calls the appropriate function, and returns the result as JSON.
        """
        try:
            # Validate and sanitize arguments before calling the tool
            validated_args = self._validate_and_sanitize_args(func_name, func_args)
            
            if not validated_args:
                return json.dumps({"error": f"Argument validation failed for {func_name}"})

            tool_func = getattr(self.trading_funcs, func_name, None)
            if not tool_func:
                return json.dumps({"error": f"Tool function '{func_name}' not found."})

            # Execute the tool function
            if asyncio.iscoroutinefunction(tool_func):
                result = await tool_func(**validated_args)
            else:
                result = tool_func(**validated_args)
            
            # Special handling for order placement to manage state and return relevant info
            if func_name == "place_order" and isinstance(result, dict) and result.get("status") == "success":
                order = result.get("order")
                if order:
                    self.order_manager[order.client_order_id] = order
                    # Return order details in a format Gemini can understand
                    return json.dumps({"status": "success", "order_details": order.to_dict()})
            
            # For other tool calls, return the result directly
            return json.dumps(result)

        except Exception as e:
            logger.error(f"Error executing tool call '{func_name}': {e}")
            return json.dumps({"error": str(e)})

    def _validate_and_sanitize_args(self, func_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates and sanitizes arguments for tool calls.
        This is a placeholder; a more robust implementation would use Pydantic models.
        """
        validated_args = {}
        
        # Define expected parameters and their validation/sanitization rules
        param_rules = {
            "get_real_time_market_data": {
                "symbol": {"type": str, "upper": True, "strip": True, "min_len": 1, "max_len": 20},
                "timeframe": {"type": str, "default": "1m"}
            },
            "calculate_advanced_indicators": {
                "symbol": {"type": str, "upper": True, "strip": True, "min_len": 1, "max_len": 20},
                "period": {"type": int, "default": 14, "min": 5, "max": 200}
            },
            "get_portfolio_status": {
                "account_id": {"type": str, "default": "default_account"}
            },
            "execute_risk_analysis": {
                "symbol": {"type": str, "upper": True, "strip": True, "min_len": 1, "max_len": 20},
                "position_size": {"type": float, "min": 0.000001},
                "entry_price": {"type": float, "min": 0.000001},
                "stop_loss": {"type": float, "min": 0.000001, "optional": True},
                "take_profit": {"type": float, "min": 0.000001, "optional": True}
            },
            "place_order": {
                "symbol": {"type": str, "upper": True, "strip": True, "min_len": 1, "max_len": 20},
                "side": {"type": str, "enum": ["Buy", "Sell"]},
                "order_type": {"type": str, "enum": ["Limit", "Market", "StopLimit"]},
                "qty": {"type": float, "min": 0.000001},
                "price": {"type": float, "min": 0.000001, "optional": True},
                "stop_loss": {"type": float, "min": 0.000001, "optional": True},
                "take_profit": {"type": float, "min": 0.000001, "optional": True},
                "client_order_id": {"type": str, "optional": True}
            },
            "cancel_order": {
                "symbol": {"type": str, "upper": True, "strip": True, "min_len": 1, "max_len": 20},
                "order_id": {"type": str, "optional": True},
                "client_order_id": {"type": str, "optional": True}
            }
        }

        rules = param_rules.get(func_name, {})

        for param_name, rule in rules.items():
            value = args.get(param_name)

            if value is None:
                if rule.get("optional", False):
                    continue # Skip optional parameters not provided
                elif "default" in rule:
                    value = rule["default"]
                else:
                    raise ValueError(f"Missing required parameter '{param_name}' for function '{func_name}'.")
            
            # Type conversion and validation
            try:
                if rule["type"] == str:
                    processed_value = str(value)
                    if rule.get("upper"): processed_value = processed_value.upper()
                    if rule.get("strip"): processed_value = processed_value.strip()
                    if rule.get("min_len") is not None and len(processed_value) < rule["min_len"]:
                        raise ValueError(f"Parameter '{param_name}' too short.")
                    if rule.get("max_len") is not None and len(processed_value) > rule["max_len"]:
                        raise ValueError(f"Parameter '{param_name}' too long.")
                elif rule["type"] == float:
                    processed_value = float(value)
                    if rule.get("min") is not None and processed_value < rule["min"]:
                        raise ValueError(f"Parameter '{param_name}' cannot be less than {rule['min']}.")
                    if rule.get("max") is not None and processed_value > rule["max"]:
                        raise ValueError(f"Parameter '{param_name}' cannot be greater than {rule['max']}.")
                elif rule["type"] == int:
                    processed_value = int(value)
                    if rule.get("min") is not None and processed_value < rule["min"]:
                        raise ValueError(f"Parameter '{param_name}' cannot be less than {rule['min']}.")
                    if rule.get("max") is not None and processed_value > rule["max"]:
                        raise ValueError(f"Parameter '{param_name}' cannot be greater than {rule['max']}.")
                elif rule["type"] == bool:
                    processed_value = bool(value)
                else:
                    processed_value = value # No specific rule, pass through

                # Enum validation
                if "enum" in rule and processed_value not in rule["enum"]:
                    raise ValueError(f"Parameter '{param_name}' must be one of {rule['enum']}.")

                validated_args[param_name] = processed_value

            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid value for parameter '{param_name}': {e}")

        # Add any arguments not explicitly defined in rules, if they are allowed
        # This part might need refinement based on how Gemini passes arguments.
        # For now, we assume rules cover all expected parameters.
        
        return validated_args

    def track_token_usage(self, response):
        """Tracks token usage and estimates cost for Gemini API calls."""
        usage = getattr(response, "usage_metadata", None)
        if not usage:
            return {}, 0.0
        usage_breakdown = {
            "input_tokens": getattr(usage, "prompt_token_count", 0),
            "output_tokens": getattr(usage, "candidates_token_count", 0),
            "cached_tokens": getattr(usage, "cached_content_token_count", 0),
            "total_tokens": getattr(usage, "total_token_count", 0)
        }
        # Example pricing; replace with your current rates.
        est_cost = (
            usage_breakdown["input_tokens"] * 0.000125 +  # $0.125 per 1M tokens
            usage_breakdown["output_tokens"] * 0.000375 +  # $0.375 per 1M tokens
            usage_breakdown["cached_tokens"] * 0.00003125  # 75% discount on cached
        ) / 1000.0
        logger.info(f"Gemini Token usage: {usage_breakdown}  est_cost=${est_cost:.6f}")
        return usage_breakdown, est_cost

    def validate_token_limits(self, prompt: str, limit: int = 1_000_000) -> bool:
        """Checks if a prompt exceeds the token limit using Gemini's count_tokens API."""
        if not self.gemini_api_key:
            logger.warning("Gemini API key not set. Cannot validate token limits.")
            return True # Assume valid if API key is missing

        try:
            count = self.gemini_client.models.count_tokens(model=self.model_id, contents=prompt)
            if count.total_tokens > limit:
                logger.warning(f"Prompt exceeds token limit: {count.total_tokens} > {limit}")
                return False
            return True
        except Exception as e:
            logger.error(f"Error counting tokens: {e}")
            return False

    async def batch_symbol_analysis(self, symbols: List[str]) -> Dict[str, Any]:
        """Analyzes multiple symbols efficiently using caching and token limit checks."""
        results = {}
        for s in symbols:
            # Check token limits before making the call
            if not self.validate_token_limits(f"Analyze {s}"):
                logger.warning(f"Skipping analysis for {s} due to token limit.")
                continue
            
            resp = await self.perform_quantitative_analysis(s)
            usage, cost = self.track_token_usage(resp)
            results[s] = {"analysis": resp, "token_usage": usage, "cost": cost}
        return results

    # --- Execution of AI-suggested trades ---
    async def execute_ai_trade_suggestion(self, symbol: str, side: str, order_type: str, qty: float, price: Optional[float] = None, stop_loss: Optional[float] = None, take_profit: Optional[float] = None):
        """
        Executes a trade based on AI suggestion, after risk policy validation.
        This function would be called when the AI proposes a trade.
        """
        if not self.bybit_adapter or not self.risk_policy:
            logger.error("Cannot execute trade: Bybit adapter or risk policy not initialized.")
            return {"status": "failed", "message": "Trading system not fully initialized."}

        # 1. Validate the trade proposal against risk policies
        is_valid, reason = await self.risk_policy.validate_trade_proposal(
            symbol, side, order_type, qty, price, stop_loss, take_profit
        )

        if not is_valid:
            logger.warning(f"Trade proposal rejected by risk policy: {reason}")
            return {"status": "rejected", "reason": reason}

        # 2. Place the order using the Bybit adapter
        # Generate a unique client order ID for idempotency
        client_order_id = f"AI_{symbol}_{side}_{order_type}_{int(time.time())}_{np.random.randint(1000, 9999)}"
        
        # Ensure price is provided for Limit/StopLimit orders
        if order_type in ["Limit", "StopLimit"] and price is None:
            return {"status": "failed", "message": f"Price is required for {order_type} orders."}
        
        # Ensure stop_loss and take_profit are floats if provided
        stop_loss_float = float(stop_loss) if stop_loss is not None else None
        take_profit_float = float(take_profit) if take_profit is not None else None

        # Ensure quantity is float
        qty_float = float(qty)

        # Call the Bybit adapter's place_order method
        order_result = self.bybit_adapter.place_order( # place_order is synchronous
            symbol=symbol,
            side=side,
            order_type=order_type,
            qty=qty_float,
            price=price,
            stop_loss=stop_loss_float,
            take_profit=take_profit_float,
            client_order_id=client_order_id
        )
        
        # Store the order in our manager
        if order_result.get("status") == "success":
            order = order_result.get("order")
            if order:
                self.order_manager[order.client_order_id] = order
                logger.info(f"Trade executed successfully: {order.client_order_id} ({order.status})")
                return {"status": "success", "order": order.to_dict()}
            else:
                logger.error("Order placement reported success but no order object returned.")
                return {"status": "failed", "message": "Order placement reported success but no order object returned."}
        else:
            logger.error(f"Trade execution failed: {order_result.get('message')}")
            return {"status": "failed", "message": order_result.get('message')}

# --- Example Usage ---
async def main():
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY environment variable not set. Please set it.")
        return
    if not BYBIT_INTEGRATION_ENABLED:
        logger.error("Pybit library not installed. Cannot run Bybit examples.")
        return
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        logger.error("BYBIT_API_KEY or BYBIT_API_SECRET environment variables not set. Cannot run Bybit examples.")
        return

    # Initialize the trading system
    system = TradingAISystem(api_key=GEMINI_API_KEY)
    await system.initialize()

    # --- Example 1: Perform Quantitative Analysis ---
    logger.info("\n--- Performing Quantitative Analysis for BTCUSDT ---")
    analysis_response = await system.perform_quantitative_analysis("BTCUSDT")
    # You can parse analysis_response here to extract data_summary, indicators, trade_plan etc.
    # For brevity, we'll just log that it was performed.
    logger.info("Quantitative analysis completed.")

    # --- Example 2: Analyze a Chart (requires a chart image file) ---
    # Create a dummy image file for demonstration if it doesn't exist
    dummy_chart_path = "dummy_chart.png"
    if not os.path.exists(dummy_chart_path):
        try:
            from PIL import Image, ImageDraw
            img = Image.new('RGB', (60, 30), color = (255, 255, 255))
            d = ImageDraw.Draw(img)
            d.text((10,10), "Chart", fill=(0,0,0))
            img.save(dummy_chart_path)
            logger.info(f"Created dummy chart image: {dummy_chart_path}")
        except ImportError:
            logger.warning("Pillow not installed. Cannot create dummy chart image. Skipping chart analysis example.")
            dummy_chart_path = None

    if dummy_chart_path and os.path.exists(dummy_chart_path):
        logger.info("\n--- Analyzing Market Chart for ETHUSDT ---")
        chart_analysis = await system.analyze_market_charts(dummy_chart_path, "ETHUSDT")
        logger.info(f"Chart Analysis Result: {json.dumps(chart_analysis, indent=2)}")
        # Clean up dummy file
        # os.remove(dummy_chart_path)

    # --- Example 3: Simulate Trade Execution ---
    logger.info("\n--- Simulating Trade Execution ---")
    symbol_to_trade = "BTCUSDT"
    
    # Fetch current market data to get a price for the trade suggestion
    market_data = system.bybit_adapter.get_real_time_market_data(symbol_to_trade)
    current_price = market_data.get("price")
    
    if current_price:
        logger.info(f"Current price for {symbol_to_trade}: {current_price}")
        
        # Simulate an AI suggestion for a BUY LIMIT order
        ai_suggested_side = "Buy"
        ai_suggested_order_type = "Limit"
        ai_suggested_qty = 0.001 # Example quantity
        ai_suggested_entry_price = current_price * 0.99 # 1% below current price
        ai_suggested_stop_loss = ai_suggested_entry_price * 0.98 # 2% below entry
        ai_suggested_take_profit = ai_suggested_entry_price * 1.05 # 5% above entry

        logger.info(f"Simulating AI suggestion: {ai_suggested_side} {ai_suggested_order_type} {ai_suggested_qty} @ {ai_suggested_entry_price} (SL: {ai_suggested_stop_loss}, TP: {ai_suggested_take_profit})")

        # Execute the trade suggestion through the system
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

        # Example of checking order status
        if trade_execution_result.get("status") == "success":
            order_id_to_check = trade_execution_result["order"]["bybit_order_id"]
            client_id_to_check = trade_execution_result["order"]["client_order_id"]
            logger.info(f"\n--- Checking status of order {client_id_to_check} ---")
            updated_order = system.bybit_adapter.get_order(symbol_to_trade, order_id=order_id_to_check, client_order_id=client_id_to_check)
            if updated_order:
                logger.info(f"Updated order status: {updated_order.status}")
            else:
                logger.warning("Could not retrieve updated order status.")
        
        # Example of cancelling an order (if it was placed and is still open)
        # if trade_execution_result.get("status") == "success" and trade_execution_result["order"]["status"] == "ORDER_PLACED":
        #     logger.info(f"\n--- Attempting to cancel order {trade_execution_result['order']['client_order_id']} ---")
        #     cancel_result = system.bybit_adapter.cancel_order(
        #         symbol=symbol_to_trade,
        #         client_order_id=trade_execution_result["order"]["client_order_id"]
        #     )
        #     logger.info(f"Cancel Order Result: {cancel_result}")

    else:
        logger.warning(f"Could not fetch current price for {symbol_to_trade}. Skipping trade simulation.")

    # --- Example 4: Start Live Trading Session (Uncomment to run) ---
    # logger.info("\n--- Starting Live Trading Session ---")
    # await system.start_live_trading_session()
    # logger.info("Live trading session ended.")

if __name__ == "__main__":
    # Ensure you have set your GEMINI_API_KEY and BYBIT_API_KEY/BYBIT_API_SECRET environment variables
    # Example:
    # export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
    # export BYBIT_API_KEY="YOUR_BYBIT_API_KEY"
    # export BYBIT_API_SECRET="YOUR_BYBIT_API_SECRET"
    
    # For testing purposes, you might want to mock Bybit API calls if you don't have keys or want to avoid live trading.
    
    asyncio.run(main())
  
