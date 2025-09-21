"Bybit Ultra Scalper Bot: A comprehensive, enterprise-grade trading bot for Bybit exchange.

This bot leverages Ehlers Fisher Transform and SuperTrend indicators for signal generation,
and manages orders, positions, and WebSocket connections with enhanced robustness and logging.
"

import json
import time
import requests
import hmac
import hashlib
import asyncio
import websockets
import pandas as pd
import logging
from datetime import timezone

# Import configuration and custom indicators
import config
from indicators import EhlersFilter, SuperTrend

# Import specific TA indicators directly
from ta.momentum import RSIIndicator, StochasticOscillator

# --- Logging Setup ---
# Configure logging to output to console and a file
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
root_logger = logging.getLogger()
root_logger.setLevel(config.LOG_LEVEL)

# Console Handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
root_logger.addHandler(console_handler)

# File Handler
file_handler = logging.FileHandler(config.LOG_FILE)
file_handler.setFormatter(log_formatter)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)


class BybitClient:
    """Handles interactions with the Bybit REST API for trading and account management."""

    def __init__(self, api_key: str, api_secret: str, base_url: str):
        """Initializes the BybitClient.

        Args:
            api_key: Your Bybit API key.
            api_secret: Your Bybit API secret.
            base_url: The base URL for the Bybit REST API (testnet or mainnet).
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.session = requests.Session()
        logger.info(f"BybitClient initialized for base URL: {self.base_url}")

    def _generate_signature(self, payload: dict) -> str:
        """Generates the HMAC SHA256 signature for a request payload."""
        param_str = '&'.join([f'{k}={v}' for k, v in sorted(payload.items())
                               if v is not None])
        return hmac.new(self.api_secret.encode('utf-8'),
                        param_str.encode('utf-8'),
                        hashlib.sha256).hexdigest()

    def send_signed_request(self, method: str, endpoint: str,
                            payload: dict = None) -> dict | None:
        """Sends a signed request to the Bybit API.

        Args:
            method: HTTP method (GET or POST).
            endpoint: API endpoint path.
            payload: Dictionary of request parameters.

        Returns:
            JSON response from the API or None if an error occurred.
        """
        if payload is None:
            payload = {}

        # Add common parameters
        payload['api_key'] = self.api_key
        payload['timestamp'] = int(time.time() * 1000)
        payload['recv_window'] = 5000  # Default recv_window

        signature = self._generate_signature(payload)
        payload['sign'] = signature

        headers = {'Content-Type': 'application/json'}
        url = f"{self.base_url}{endpoint}"

        try:
            if method == 'GET':
                response = self.session.get(url, params=payload,
                                            headers=headers, timeout=10)
            elif method == 'POST':
                response = self.session.post(url, json=payload,
                                             headers=headers, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()  # Raise HTTPError for bad responses
            return response.json()
        except requests.exceptions.Timeout:
            logger.error(f"Request to {url} timed out after 10 seconds.")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}, "
                             f"content: {e.response.text}")
            return None
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from response: {response.text}")
            return None

    def send_public_request(self, method: str, endpoint: str,
                            params: dict = None) -> dict | None:
        """Sends a public (unsigned) request to the Bybit API.

        Args:
            method: HTTP method (GET).
            endpoint: API endpoint path.
            params: Dictionary of request parameters.

        Returns:
            JSON response from the API or None if an error occurred.
        """
        if params is None:
            params = {}
        url = f"{self.base_url}{endpoint}"
        try:
            if method == 'GET':
                response = self.session.get(url, params=params, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method for public request: "
                                 f"{method}")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.error(f"Public request to {url} timed out after 10 seconds.")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Public request failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}, "
                             f"content: {e.response.text}")
            return None
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from response: {response.text}")
            return None

    def get_kline(self, symbol: str, interval: str, limit: int = 200,
                  end_time: int = None) -> list | None:
        """Fetches kline (candlestick) data.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT").
            interval: Candlestick interval (e.g., "1", "5", "60").
            limit: Number of candlesticks to retrieve.
            end_time: End timestamp for the data (in milliseconds).

        Returns:
            List of kline data or None.
        """
        endpoint = "/v5/market/kline"
        params = {
            'category': 'linear',
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        if end_time:
            params['end'] = end_time

        response = self.send_public_request('GET', endpoint, params)
        if response and response['retCode'] == 0:
            return response['result']['list']
        logger.error(f"Failed to get kline data: {response}")
        return None

    def place_order(self, symbol: str, side: str, qty: float,
                    order_type: str = "Market", price: float = None,
                    time_in_force: str = "GTC", reduce_only: bool = False,
                    close_on_trigger: bool = False, stop_loss_px: float = None,
                    take_profit_px: float = None) -> dict | None:
        """Places a new order on the exchange.

        Args:
            symbol: Trading pair symbol.
            side: Order side ("Buy" or "Sell").
            qty: Order quantity.
            order_type: Type of order ("Market" or "Limit").
            price: Price for limit orders.
            time_in_force: Time in force policy (e.g., "GTC", "IOC").
            reduce_only: Whether the order is reduce-only.
            close_on_trigger: Whether to close position on trigger.
            stop_loss_px: Stop loss price.
            take_profit_px: Take profit price.

        Returns:
            Order placement response or None.
        """
        endpoint = "/v5/order/create"
        payload = {
            'category': 'linear',
            'symbol': symbol,
            'side': side,
            'orderType': order_type,
            'qty': str(qty),
            'timeInForce': time_in_force,
            'reduceOnly': reduce_only,
            'closeOnTrigger': close_on_trigger,
            'isLeverage': 1,  # For isolated margin
            'triggerDirection': 1 if side == 'Buy' else 2  # For TP/SL
        }
        if price:
            payload['price'] = str(price)
        if stop_loss_px:
            payload['stopLoss'] = str(stop_loss_px)
        if take_profit_px:
            payload['takeProfit'] = str(take_profit_px)

        response = self.send_signed_request('POST', endpoint, payload)
        if response and response['retCode'] == 0:
            logger.info(f"Order placed successfully: {response['result']}")
            return response['result']
        logger.error(f"Failed to place order: {response}")
        return None

    def get_open_orders(self, symbol: str) -> list | None:
        """Retrieves a list of open orders for a given symbol."""
        endpoint = "/v5/order/realtime"
        params = {
            'category': 'linear',
            'symbol': symbol,
        }
        response = self.send_signed_request('GET', endpoint, params)
        if response and response['retCode'] == 0:
            return response['result']['list']
        logger.error(f"Failed to get open orders: {response}")
        return None

    def cancel_order(self, symbol: str, order_id: str = None,
                     order_link_id: str = None) -> dict | None:
        """Cancels an active order by order ID or order link ID."""
        endpoint = "/v5/order/cancel"
        payload = {
            'category': 'linear',
            'symbol': symbol,
        }
        if order_id:
            payload['orderId'] = order_id
        if order_link_id:
            payload['orderLinkId'] = order_link_id

        response = self.send_signed_request('POST', endpoint, payload)
        if response and response['retCode'] == 0:
            logger.info(f"Order cancelled successfully: {response['result']}")
            return response['result']
        logger.error(f"Failed to cancel order: {response}")
        return None

    def get_position(self, symbol: str) -> dict | None:
        """Retrieves the current position for a given symbol."""
        endpoint = "/v5/position/list"
        params = {
            'category': 'linear',
            'symbol': symbol,
        }
        response = self.send_signed_request('GET', endpoint, params)
        if response and response['retCode'] == 0:
            if response['result']['list']:
                # Assuming only one position per symbol
                return response['result']['list'][0]
            return None
        logger.error(f"Failed to get position: {response}")
        return None

    def set_leverage(self, symbol: str, leverage: float) -> bool:
        """Sets the leverage for a trading pair."""
        endpoint = "/v5/position/set-leverage"
        payload = {
            'category': 'linear',
            'symbol': symbol,
            'buyLeverage': str(leverage),
            'sellLeverage': str(leverage)
        }
        response = self.send_signed_request('POST', endpoint, payload)
        if response and response['retCode'] == 0:
            logger.info(f"Leverage set to {leverage} for {symbol}")
            return True
        logger.error(f"Failed to set leverage: {response}")
        return False

    def get_wallet_balance(self, account_type: str = "UNIFIED") -> dict | None:
        """Retrieves wallet balance information."""
        endpoint = "/v5/account/wallet-balance"
        params = {
            'accountType': account_type
        }
        response = self.send_signed_request('GET', endpoint, params)
        if response and response['retCode'] == 0:
            return response['result']['list'][0]
        logger.error(f"Failed to get wallet balance: {response}")
        return None


class EhlersSupertrendStrategy:
    """Implements a trading strategy using Ehlers Fisher Transform and SuperTrend."""

    def __init__(self, client: BybitClient, symbol: str, interval: str,
                 trade_qty: float, leverage: float, rsi_period: int,
                 rsi_overbought: float, rsi_oversold: float,
                 stoch_rsi_period: int, stoch_rsi_smooth_k: int,
                 stoch_rsi_smooth_d: int, stoch_rsi_overbought: float,
                 stoch_rsi_oversold: float, super_trend_period: int,
                 super_trend_multiplier: float, eh_fisher_period: int,
                 eh_fisher_smoothing: int, eh_fisher_overbought: float,
                 eh_fisher_oversold: float, eh_fisher_trigger_buy: float,
                 eh_fisher_trigger_sell: float, max_position_size: float,
                 stop_loss_percent: float, take_profit_percent: float):
        """Initializes the EhlersSupertrendStrategy.

        Args:
            client: An instance of BybitClient.
            symbol: Trading pair symbol.
            interval: Candlestick interval.
            trade_qty: Quantity to trade per order.
            leverage: Leverage to use.
            rsi_period: Period for RSI calculation.
            rsi_overbought: RSI overbought threshold.
            rsi_oversold: RSI oversold threshold.
            stoch_rsi_period: Period for Stochastic RSI calculation.
            stoch_rsi_smooth_k: Smoothing for Stochastic RSI %K.
            stoch_rsi_smooth_d: Smoothing for Stochastic RSI %D.
            stoch_rsi_overbought: Stochastic RSI overbought threshold.
            stoch_rsi_oversold: Stochastic RSI oversold threshold.
            super_trend_period: Period for SuperTrend calculation.
            super_trend_multiplier: Multiplier for SuperTrend ATR.
            eh_fisher_period: Period for Ehlers Fisher Transform.
            eh_fisher_smoothing: Smoothing for Ehlers Fisher Transform.
            eh_fisher_overbought: Ehlers Fisher overbought threshold.
            eh_fisher_oversold: Ehlers Fisher oversold threshold.
            eh_fisher_trigger_buy: Ehlers Fisher buy trigger level.
            eh_fisher_trigger_sell: Ehlers Fisher sell trigger level.
            max_position_size: Maximum allowed position size.
            stop_loss_percent: Percentage for stop loss calculation.
            take_profit_percent: Percentage for take profit calculation.
        """
        self.client = client
        self.symbol = symbol
        self.interval = interval
        self.trade_qty = trade_qty
        self.leverage = leverage
        self.max_position_size = max_position_size
        self.stop_loss_percent = stop_loss_percent
        self.take_profit_percent = take_profit_percent

        self.ehlers_filter = EhlersFilter(period=eh_fisher_period,
                                          smoothing=eh_fisher_smoothing)
        self.super_trend = SuperTrend(period=super_trend_period,
                                      multiplier=super_trend_multiplier)

        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold

        self.stoch_rsi_period = stoch_rsi_period
        self.stoch_rsi_smooth_k = stoch_rsi_smooth_k
        self.stoch_rsi_smooth_d = stoch_rsi_smooth_d
        self.stoch_rsi_overbought = stoch_rsi_overbought
        self.stoch_rsi_oversold = stoch_rsi_oversold

        self.eh_fisher_overbought = eh_fisher_overbought
        self.eh_fisher_oversold = eh_fisher_oversold
        self.eh_fisher_trigger_buy = eh_fisher_trigger_buy
        self.eh_fisher_trigger_sell = eh_fisher_trigger_sell

        self.df = pd.DataFrame()
        self.in_position = False
        self.position_side = None  # 'Buy' or 'Sell'
        self.position_qty = 0.0
        self.entry_price = 0.0

        logger.info(f"Strategy initialized for {symbol} with interval {interval}")

    async def initialize_data(self):
        """Fetches initial historical data and calculates indicators."""
        logger.info(f"Initializing historical data for {self.symbol}...")
        klines = self.client.get_kline(self.symbol, self.interval, limit=200)
        if klines:
            self.df = self._process_kline_data(klines)
            self.df = self._calculate_indicators(self.df)
            logger.info(f"Historical data initialized. Current DF size: "
                        f"{len(self.df)}")
        else:
            logger.error("Failed to fetch initial kline data.")
            raise Exception("Initial data fetch failed.")

    def _process_kline_data(self, kline_data_list: list) -> pd.DataFrame:
        """Processes raw kline data into a pandas DataFrame."""
        # Ensure kline_data_list is a list of lists/tuples
        if not isinstance(kline_data_list, list) or not all(isinstance(k, list)
                                                           for k in kline_data_list):
            logger.error(f"Invalid kline data format: {kline_data_list}")
            return pd.DataFrame()

        df = pd.DataFrame(kline_data_list, columns=[
            'start_time', 'open', 'high', 'low', 'close', 'volume', 'turnover'
        ])
        df['start_time'] = pd.to_datetime(df['start_time'], unit='ms', utc=True)
        df[['open', 'high', 'low', 'close', 'volume', 'turnover']] = \
            df[['open', 'high', 'low', 'close', 'volume', 'turnover']].astype(float)
        df = df.set_index('start_time')

        # Ensure index is unique and sorted
        df = df[~df.index.duplicated(keep='last')]
        return df.sort_index()

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates all necessary technical indicators for the strategy."""
        if df.empty:
            return df

        # Ensure the DataFrame has the required columns for ta library
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required_cols):
            logger.warning("DataFrame missing required columns for TA indicators. "
                           "Skipping calculation.")
            return df

        # RSI
        df['rsi'] = RSIIndicator(df['close'], window=self.rsi_period).rsi()

        # Stochastic RSI
        stoch_rsi = StochasticOscillator(
            df['close'], window=self.stoch_rsi_period,
            smooth_window=self.stoch_rsi_smooth_k, fillna=False
        )
        df['stoch_rsi_k'] = stoch_rsi.stoch_signal()  # K line
        df['stoch_rsi_d'] = stoch_rsi.stoch()  # D line (often called %D or main StochRSI line)

        # Ehlers Fisher Transform (using custom class)
        df = self.ehlers_filter.calculate(df)

        # SuperTrend (using custom class)
        df = self.super_trend.calculate(df)

        # Drop any NaN values that result from indicator calculations
        df.dropna(inplace=True)
        return df

    async def update_data(self, kline_data: list):
        """Updates the DataFrame with new kline data and recalculates indicators."""
        new_kline_df = self._process_kline_data([kline_data])
        if new_kline_df.empty:
            logger.warning("Received empty or invalid kline data for update.")
            return

        # Check if the new kline is a duplicate or older
        if not self.df.empty and new_kline_df.index.max() <= self.df.index.max():
            # If it's an update to the latest candle, replace it
            if new_kline_df.index.max() == self.df.index.max():
                self.df.update(new_kline_df)
                logger.debug(f"Updated latest kline: {new_kline_df.index.max()}")
            else:
                logger.debug(f"Received old kline data, ignoring: "
                             f"{new_kline_df.index.max()}")
                return
        else:
            # Append new kline and keep only the last 200 for performance
            self.df = pd.concat([self.df, new_kline_df]).iloc[-200:]
            logger.debug(f"Appended new kline: {new_kline_df.index.max()}")

        self.df = self._calculate_indicators(self.df)
        logger.debug(f"Data updated and indicators recalculated. Current DF size: "
                     f"{len(self.df)}")

    async def check_and_execute_trade(self):
        """Checks for trade signals and executes trades based on strategy rules."""
        min_data_len = max(self.rsi_period, self.stoch_rsi_period,
                           self.ehlers_filter.period, self.super_trend.period) + 1
        if self.df.empty or len(self.df) < min_data_len:
            logger.warning("Not enough data to generate signals.")
            return

        latest_candle = self.df.iloc[-1]

        # --- Signal Generation ---
        buy_signal = False
        sell_signal = False

        # Ehlers Fisher Buy Signal: Fisher crosses above signal and trigger,
        # and is not overbought
        eh_fisher_buy_condition = (
            latest_candle['eh_fisher'] > latest_candle['eh_fisher_signal']
            and latest_candle['eh_fisher_signal'] < self.eh_fisher_trigger_buy
            and latest_candle['eh_fisher'] < self.eh_fisher_overbought
        )

        # Ehlers Fisher Sell Signal: Fisher crosses below signal and trigger,
        # and is not oversold
        eh_fisher_sell_condition = (
            latest_candle['eh_fisher'] < latest_candle['eh_fisher_signal']
            and latest_candle['eh_fisher_signal'] > self.eh_fisher_trigger_sell
            and latest_candle['eh_fisher'] > self.eh_fisher_oversold
        )

        # SuperTrend Buy Signal: Close above SuperTrend and SuperTrend direction is up
        supertrend_buy_condition = (
            latest_candle['close'] > latest_candle['supertrend']
            and latest_candle['supertrend_direction'] == 1
        )

        # SuperTrend Sell Signal: Close below SuperTrend and SuperTrend direction is down
        supertrend_sell_condition = (
            latest_candle['close'] < latest_candle['supertrend']
            and latest_candle['supertrend_direction'] == -1
        )

        # Combined Buy Signal
        if eh_fisher_buy_condition and supertrend_buy_condition:
            buy_signal = True
            logger.info("Combined BUY signal detected!")

        # Combined Sell Signal
        if eh_fisher_sell_condition and supertrend_sell_condition:
            sell_signal = True
            logger.info("Combined SELL signal detected!")

        # --- Position Management ---
        current_position = self.client.get_position(self.symbol)
        if current_position:
            self.in_position = True
            self.position_qty = float(current_position['size'])
            self.position_side = current_position['side']
            self.entry_price = float(current_position['avgPrice'])
            logger.info(f"Current position: {self.position_side} "
                        f"{self.position_qty} at {self.entry_price}")
        else:
            self.in_position = False
            self.position_qty = 0.0
            self.position_side = None
            self.entry_price = 0.0
            logger.info("No open position.")

        if not self.in_position:
            if buy_signal:
                await self._execute_trade('Buy')
            elif sell_signal:
                await self._execute_trade('Sell')
        else:
            # Check for reversal or exit conditions
            if self.position_side == 'Buy' and sell_signal:
                logger.info("Reversal: Buy position open, but sell signal detected. "
                            "Closing position and opening sell.")
                await self._close_position()
                await self._execute_trade('Sell')
            elif self.position_side == 'Sell' and buy_signal:
                logger.info("Reversal: Sell position open, but buy signal detected. "
                            "Closing position and opening buy.")
                await self._close_position()
                await self._execute_trade('Buy')
            else:
                logger.info("No new trade signals or reversal detected. "
                            "Holding current position.")

    async def _execute_trade(self, side: str):
        """Executes a trade (buy or sell) with calculated stop loss and take profit."""
        if self.position_qty >= self.max_position_size:
            logger.warning(f"Cannot open {side} trade: Max position size reached "
                           f"({self.position_qty}).")
            return

        # Calculate quantity to trade, ensuring it doesn't exceed max_position_size
        qty_to_trade = min(self.trade_qty,
                           self.max_position_size - self.position_qty)
        if qty_to_trade <= 0:
            logger.warning(f"Calculated trade quantity is zero or negative for "
                           f"{side} trade.")
            return

        # Get current price for SL/TP calculation
        current_price = self.df['close'].iloc[-1]

        stop_loss_px = None
        take_profit_px = None

        if side == 'Buy':
            stop_loss_px = current_price * (1 - self.stop_loss_percent)
            take_profit_px = current_price * (1 + self.take_profit_percent)
        elif side == 'Sell':
            stop_loss_px = current_price * (1 + self.stop_loss_percent)
            take_profit_px = current_price * (1 - self.take_profit_percent)

        logger.info(f"Attempting to place {side} order for {qty_to_trade} "
                    f"{self.symbol} with SL: {stop_loss_px:.2f}, "
                    f"TP: {take_profit_px:.2f}")

        order_result = self.client.place_order(
            symbol=self.symbol,
            side=side,
            qty=qty_to_trade,
            order_type="Market",
            stop_loss_px=stop_loss_px,
            take_profit_px=take_profit_px
        )

        if order_result:
            self.in_position = True
            self.position_side = side
            self.position_qty += qty_to_trade
            # For market orders, entry price is close price
            self.entry_price = current_price
            logger.info(f"Successfully opened {side} position of {qty_to_trade} "
                        f"{self.symbol}.")
        else:
            logger.error(f"Failed to open {side} position.")

    async def _close_position(self):
        """Closes the current open position."""
        if not self.in_position or self.position_qty == 0:
            logger.info("No open position to close.")
            return

        # Determine opposite side to close the position
        close_side = 'Sell' if self.position_side == 'Buy' else 'Buy'

        logger.info(f"Attempting to close {self.position_side} position of "
                    f"{self.position_qty} {self.symbol}.")

        order_result = self.client.place_order(
            symbol=self.symbol,
            side=close_side,
            qty=self.position_qty,
            order_type="Market",
            reduce_only=True  # Ensure this order only reduces position
        )

        if order_result:
            self.in_position = False
            self.position_qty = 0.0
            self.position_side = None
            self.entry_price = 0.0
            logger.info(f"Successfully closed position for {self.symbol}.")
        else:
            logger.error(f"Failed to close position for {self.symbol}.")


class WebSocketClient:
    """Manages WebSocket connections for real-time market and account data."""

    def __init__(self, public_ws_url: str, private_ws_url: str, api_key: str,
                 api_secret: str, strategy: EhlersSupertrendStrategy):
        """Initializes the WebSocketClient.

        Args:
            public_ws_url: URL for public WebSocket.
            private_ws_url: URL for private WebSocket.
            api_key: Bybit API key.
            api_secret: Bybit API secret.
            strategy: The trading strategy instance to update.
        """
        self.public_ws_url = public_ws_url
        self.private_ws_url = private_ws_url
        self.api_key = api_key
        self.api_secret = api_secret
        self.strategy = strategy
        self.public_websocket = None
        self.private_websocket = None
        self.is_connected = False
        self.reconnect_attempt = 0
        self.last_ping_time = time.time()
        logger.info(f"WebSocketClient initialized. Public WS: {self.public_ws_url}, "
                    f"Private WS: {self.private_ws_url}")

    async def _connect_public(self) -> bool:
        """Establishes connection to the public WebSocket and subscribes to kline data."""
        try:
            self.public_websocket = await websockets.connect(
                self.public_ws_url, ping_interval=config.PING_INTERVAL,
                ping_timeout=config.PING_TIMEOUT)
            logger.info("Connected to public WebSocket.")
            # Subscribe to kline data
            await self.public_websocket.send(json.dumps({
                "op": "subscribe",
                "args": [f"kline.{config.INTERVAL}.{config.SYMBOL}"]
            }))
            logger.info(f"Subscribed to kline.{config.INTERVAL}.{config.SYMBOL}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to public WebSocket: {e}")
            return False

    async def _connect_private(self) -> bool:
        """Establishes connection to the private WebSocket and authenticates."""
        try:
            self.private_websocket = await websockets.connect(
                self.private_ws_url, ping_interval=config.PING_INTERVAL,
                ping_timeout=config.PING_TIMEOUT)
            logger.info("Connected to private WebSocket.")

            # Authenticate private channel
            expires = int((time.time() + 10) * 1000)
            param_str = f"GET/realtime{expires}"
            signature = hmac.new(self.api_secret.encode('utf-8'),
                                 param_str.encode('utf-8'),
                                 hashlib.sha256).hexdigest()

            await self.private_websocket.send(json.dumps({
                "op": "auth",
                "args": [self.api_key, expires, signature]
            }))
            auth_response = await self.private_websocket.recv()
            auth_data = json.loads(auth_response)
            if auth_data.get('success'):
                logger.info("Private WebSocket authenticated successfully.")
                # Subscribe to private topics (e.g., position, order)
                await self.private_websocket.send(json.dumps({
                    "op": "subscribe",
                    "args": ["position", "order"]
                }))
                logger.info("Subscribed to private topics: position, order")
                return True
            else:
                logger.error(f"Private WebSocket authentication failed: "
                             f"{auth_data}")
                return False
        except Exception as e:
            logger.error(f"Failed to connect or authenticate private WebSocket: "
                         f"{e}")
            return False

    async def connect(self) -> bool:
        """Connects to both public and private WebSockets."""
        public_connected = await self._connect_public()
        private_connected = await self._connect_private()
        self.is_connected = public_connected and private_connected
        if self.is_connected:
            self.reconnect_attempt = 0
            logger.info("All WebSockets connected.")
        else:
            logger.error("One or more WebSockets failed to connect.")
        return self.is_connected

    async def reconnect(self) -> bool:
        """Attempts to reconnect to WebSockets with exponential backoff."""
        self.is_connected = False
        self.reconnect_attempt += 1
        # Exponential backoff, max 60s
        delay = min(config.RECONNECT_TIMEOUT_SECONDS *
                    (2 ** (self.reconnect_attempt - 1)), 60)
        logger.warning(f"Reconnecting in {delay} seconds (attempt "
                       f"{self.reconnect_attempt})...")
        await asyncio.sleep(delay)
        return await self.connect()

    async def listen_public(self):
        """Listens for messages from the public WebSocket."""
        while True:
            try:
                if not self.public_websocket or not self.public_websocket.open:
                    logger.warning("Public WebSocket not open, attempting to reconnect.")
                    if not await self._connect_public():
                        await asyncio.sleep(config.RECONNECT_TIMEOUT_SECONDS)
                        continue

                message = await self.public_websocket.recv()
                data = json.loads(message)

                if 'data' in data and 'topic' in data:
                    if data['topic'].startswith('kline'):
                        await self.handle_websocket_kline_data(data['data'])
                elif 'op' in data and data['op'] == 'pong':
                    logger.debug("Received public pong.")
                else:
                    logger.debug(f"Received public message: {data}")

            except websockets.exceptions.ConnectionClosedOK:
                logger.info("Public WebSocket connection closed gracefully.")
                break
            except websockets.exceptions.ConnectionClosedError as e:
                logger.error(f"Public WebSocket connection closed with error: {e}")
                break
            except Exception as e:
                logger.error(f"Error in public WebSocket listener: {e}")
                # Prevent tight loop on errors
                await asyncio.sleep(1)

    async def listen_private(self):
        """Listens for messages from the private WebSocket."""
        while True:
            try:
                if not self.private_websocket or not self.private_websocket.open:
                    logger.warning("Private WebSocket not open, attempting to reconnect.")
                    if not await self._connect_private():
                        await asyncio.sleep(config.RECONNECT_TIMEOUT_SECONDS)
                        continue

                message = await self.private_websocket.recv()
                data = json.loads(message)

                if 'data' in data and 'topic' in data:
                    if data['topic'] == 'position':
                        logger.info(f"Position update: {data['data']}")
                        # Trigger strategy to re-evaluate position
                        await self.strategy.check_and_execute_trade()
                    elif data['topic'] == 'order':
                        logger.info(f"Order update: {data['data']}")
                        # Trigger strategy to re-evaluate position
                        await self.strategy.check_and_execute_trade()
                elif 'op' in data and data['op'] == 'pong':
                    logger.debug("Received private pong.")
                else:
                    logger.debug(f"Received private message: {data}")

            except websockets.exceptions.ConnectionClosedOK:
                logger.info("Private WebSocket connection closed gracefully.")
                break
            except websockets.exceptions.ConnectionClosedError as e:
                logger.error(f"Private WebSocket connection closed with error: {e}")
                break
            except Exception as e:
                logger.error(f"Error in private WebSocket listener: {e}")
                # Prevent tight loop on errors
                await asyncio.sleep(1)

    async def handle_websocket_kline_data(self, kline_data_list: list):
        """Handles incoming kline data from the WebSocket, updates strategy."""
        if not isinstance(kline_data_list, list):
            logger.error(f"Expected kline_data_list to be a list, got "
                         f"{type(kline_data_list)}")
            return

        for kline_data in kline_data_list:
            if not isinstance(kline_data, dict):
                logger.error(f"Expected kline_data to be a dict, got "
                             f"{type(kline_data)}")
                continue

            # Ensure the kline is closed before processing for strategy
            if kline_data.get('confirm') is True:
                logger.info(f"Processing confirmed kline: {kline_data}")
                # Convert to the format expected by _process_kline_data
                processed_kline = [
                    kline_data['start'], kline_data['open'], kline_data['high'],
                    kline_data['low'], kline_data['close'], kline_data['volume'],
                    kline_data['turnover']
                ]
                await self.strategy.update_data(processed_kline)
                await self.strategy.check_and_execute_trade()
            else:
                logger.debug(f"Received unconfirmed kline, ignoring for strategy: "
                             f"{kline_data}")

    async def run(self):
        """Main loop for running the WebSocket client and managing connections."""
        while True:
            if not self.is_connected and not await self.connect():
                continue  # Try reconnecting again after delay

            public_listener_task = asyncio.create_task(self.listen_public())
            private_listener_task = asyncio.create_task(self.listen_private())

            try:
                await asyncio.gather(public_listener_task, private_listener_task)
            except Exception as e:
                logger.error(f"Main WebSocket run loop error: {e}")
            finally:
                public_listener_task.cancel()
                private_listener_task.cancel()
                if self.public_websocket:
                    await self.public_websocket.close()
                if self.private_websocket:
                    await self.private_websocket.close()
                logger.warning("WebSockets disconnected. Attempting to reconnect...")
                await self.reconnect()

async def main():
    """Main function to initialize and run the trading bot."""
    logger.info("Starting Bybit Ultra Scalper Bot...")

    # Initialize Bybit REST client
    bybit_client = BybitClient(
        api_key=config.API_KEY,
        api_secret=config.API_SECRET,
        base_url=config.BYBIT_REST_BASE_URL
    )

    # Set leverage
    if not bybit_client.set_leverage(config.SYMBOL, config.LEVERAGE):
        logger.error("Failed to set leverage. Exiting.")
        return

    # Initialize strategy
    strategy = EhlersSupertrendStrategy(
        client=bybit_client,
        symbol=config.SYMBOL,
        interval=config.INTERVAL,
        trade_qty=config.TRADE_QTY,
        leverage=config.LEVERAGE,
        rsi_period=config.RSI_PERIOD,
        rsi_overbought=config.RSI_OVERBOUGHT,
        rsi_oversold=config.RSI_OVERSOLD,
        stoch_rsi_period=config.STOCH_RSI_PERIOD,
        stoch_rsi_smooth_k=config.STOCH_RSI_SMOOTH_K,
        stoch_rsi_smooth_d=config.STOCH_RSI_SMOOTH_D,
        stoch_rsi_overbought=config.STOCH_RSI_OVERBOUGHT,
        stoch_rsi_oversold=config.STOCH_RSI_OVERSOLD,
        super_trend_period=config.SUPER_TREND_PERIOD,
        super_trend_multiplier=config.SUPER_TREND_MULTIPLIER,
        eh_fisher_period=config.EH_FISHER_PERIOD,
        eh_fisher_smoothing=config.EH_FISHER_SMOOTHING,
        eh_fisher_overbought=config.EH_FISHER_OVERBOUGHT,
        eh_fisher_oversold=config.EH_FISHER_OVERSOLD,
        eh_fisher_trigger_buy=config.EH_FISHER_TRIGGER_BUY,
        eh_fisher_trigger_sell=config.EH_FISHER_TRIGGER_SELL,
        max_position_size=config.MAX_POSITION_SIZE,
        stop_loss_percent=config.STOP_LOSS_PERCENT,
        take_profit_percent=config.TAKE_PROFIT_PERCENT
    )

    # Fetch initial historical data
    try:
        await strategy.initialize_data()
    except Exception as e:
        logger.critical(f"Strategy initialization failed: {e}. Exiting.")
        return

    # Initialize and run WebSocket client
    ws_client = WebSocketClient(
        public_ws_url=config.BYBIT_WS_PUBLIC_BASE_URL,
        private_ws_url=config.BYBIT_WS_PRIVATE_BASE_URL,
        api_key=config.API_KEY,
        api_secret=config.API_SECRET,
        strategy=strategy
    )
    await ws_client.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt).")
    except Exception as e:
        logger.error(f"An unhandled error occurred in main: {e}", exc_info=True)
