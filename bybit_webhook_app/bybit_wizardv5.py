import hashlib
import hmac
import json
import logging
import os
import signal
import sys
import threading
import time
import traceback
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import requests
import websocket
from colorama import Fore, Style, init

# Initialize Colorama for vibrant terminal output
init()

log_file_path = os.path.expanduser("~/.bybit_logs.log")
error_log_path = os.path.expanduser("~/.bybit_errors.log")

# Create formatters
detailed_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
)
simple_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

# Setup main logger
logger = logging.getLogger("BybitWizard")
logger.setLevel(logging.INFO)

# File handler for general logs
file_handler = logging.FileHandler(log_file_path)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(detailed_formatter)

# File handler for errors
error_handler = logging.FileHandler(error_log_path)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(detailed_formatter)

# Console handler for important messages
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(simple_formatter)

logger.addHandler(file_handler)
logger.addHandler(error_handler)
logger.addHandler(console_handler)


class OrderSide(Enum):
    BUY = "Buy"
    SELL = "Sell"


class OrderType(Enum):
    MARKET = "Market"
    LIMIT = "Limit"
    CONDITIONAL = "Conditional"


class Category(Enum):
    LINEAR = "linear"
    INVERSE = "inverse"
    OPTION = "option"
    SPOT = "spot"


@dataclass
class Position:
    """Enhanced position tracking with more detailed information."""

    symbol: str
    entry_price: float | None = None
    break_even_enabled: bool = False
    tsl_enabled: bool = False
    tsl_distance: float | None = None
    profit_target: float | None = None
    profit_action: str = "partial_close"
    close_percentage: float = 50
    last_update: datetime = field(default_factory=datetime.now)
    unrealized_pnl: float | None = None
    size: float | None = None
    side: str | None = None


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""

    requests_per_minute: int = 120
    burst_limit: int = 10
    cooldown_period: float = 1.0


class TokenBucketRateLimiter:
    """Token bucket rate limiter for more sophisticated rate limiting."""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.tokens = config.burst_limit
        self.last_refill = time.time()
        self.lock = threading.Lock()

    def acquire(self, tokens: int = 1) -> bool:
        """Acquire tokens from the bucket."""
        with self.lock:
            now = time.time()
            # Refill tokens based on time elapsed
            elapsed = now - self.last_refill
            tokens_to_add = elapsed * (self.config.requests_per_minute / 60.0)
            self.tokens = min(self.config.burst_limit, self.tokens + tokens_to_add)
            self.last_refill = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def wait_for_tokens(self, tokens: int = 1, timeout: float = 30.0) -> bool:
        """Wait for tokens to become available."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.acquire(tokens):
                return True
            time.sleep(0.1)
        return False


class CircuitBreaker:
    """Circuit breaker to handle API failures gracefully."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.lock = threading.Lock()

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        with self.lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                else:
                    raise Exception("Circuit breaker is OPEN")

            try:
                result = func(*args, **kwargs)
                if self.state == "HALF_OPEN":
                    self.state = "CLOSED"
                    self.failure_count = 0
                return result
            except Exception as e:
                self.failure_count += 1
                self.last_failure_time = time.time()

                if self.failure_count >= self.failure_threshold:
                    self.state = "OPEN"

                raise e


class MetricsCollector:
    """Collect and track various metrics."""

    def __init__(self):
        self.metrics = defaultdict(int)
        self.timings = defaultdict(list)
        self.errors = defaultdict(int)
        self.lock = threading.Lock()

    def increment(self, metric: str, value: int = 1):
        """Increment a counter metric."""
        with self.lock:
            self.metrics[metric] += value

    def record_timing(self, metric: str, duration: float):
        """Record timing information."""
        with self.lock:
            self.timings[metric].append(duration)
            # Keep only last 1000 measurements
            if len(self.timings[metric]) > 1000:
                self.timings[metric] = self.timings[metric][-1000:]

    def record_error(self, error_type: str):
        """Record error occurrence."""
        with self.lock:
            self.errors[error_type] += 1

    def get_stats(self) -> dict:
        """Get current statistics."""
        with self.lock:
            stats = {
                "counters": dict(self.metrics),
                "errors": dict(self.errors),
                "timings": {},
            }

            for metric, times in self.timings.items():
                if times:
                    stats["timings"][metric] = {
                        "count": len(times),
                        "avg": sum(times) / len(times),
                        "min": min(times),
                        "max": max(times),
                    }

            return stats


class BybitV5Wizard:
    """An enhanced mystical class to wield Bybit's V5 API for trading sorcery."""

    def __init__(self, config_path: str = os.path.expanduser("~/.bybit_config")):
        """Initialize the Bybit V5 Wizard with sacred credentials from config file.

        Args:
            config_path (str): Path to JSON config file with api_key, api_secret, and testnet flag.

        """
        self.config = self._load_and_validate_config(config_path)
        self.api_key = self.config["api_key"]
        self.api_secret = self.config["api_secret"]
        self.testnet = self.config.get("testnet", False)

        self.base_url = (
            "https://api-testnet.bybit.com" if self.testnet else "https://api.bybit.com"
        )
        self.ws_public_url = (
            "wss://stream-testnet.bybit.com/v5/public/linear"
            if self.testnet
            else "wss://stream.bybit.com/v5/public/linear"
        )
        self.ws_private_url = (
            "wss://stream-testnet.bybit.com/v5/private"
            if self.testnet
            else "wss://stream.bybit.com/v5/private"
        )

        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10, pool_maxsize=20, max_retries=3,
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # WebSocket connections
        self.ws_public = None
        self.ws_private = None
        self.ws_public_thread = None
        self.ws_private_thread = None
        self.ws_reconnect_attempts = 0
        self.max_reconnect_attempts = 10

        self.positions: dict[str, Position] = {}

        self.rate_limiter = TokenBucketRateLimiter(RateLimitConfig())
        self.circuit_breaker = CircuitBreaker()
        self.metrics = MetricsCollector()

        # Threading and synchronization
        self.lock = threading.Lock()
        self.shutdown_event = threading.Event()

        self.retry_attempts = 3
        self.retry_delay = 1
        self.max_retry_delay = 30

        self.last_heartbeat = {}
        self.connection_health = {"api": True, "ws_public": False, "ws_private": False}

        logger.info(f"Bybit V5 Wizard initialized - Testnet: {self.testnet}")
        print(
            Fore.CYAN
            + "# Bybit V5 Wizard awakened with enhanced ethereal power..."
            + Style.RESET_ALL,
        )

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _load_and_validate_config(self, config_path: str) -> dict:
        """Load and validate configuration file."""
        try:
            if not os.path.exists(config_path):
                raise FileNotFoundError(f"Config file not found: {config_path}")

            with open(config_path) as f:
                config = json.load(f)

            # Validate required fields
            required_fields = ["api_key", "api_secret"]
            for field in required_fields:
                if field not in config or not config[field]:
                    raise ValueError(f"Missing or empty required field: {field}")

            # Validate API key format (basic check)
            if len(config["api_key"]) < 10:
                raise ValueError("API key appears to be invalid (too short)")

            if len(config["api_secret"]) < 10:
                raise ValueError("API secret appears to be invalid (too short)")

            logger.info("Configuration loaded and validated successfully")
            return config

        except Exception as e:
            error_msg = f"Failed to load config: {e!s}"
            logger.error(error_msg)
            raise ValueError(Fore.RED + f"# {error_msg}" + Style.RESET_ALL)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        print(Fore.YELLOW + "# Graceful shutdown initiated..." + Style.RESET_ALL)
        self.shutdown_event.set()
        self.close_ws()
        sys.exit(0)

    @contextmanager
    def _timing_context(self, operation: str):
        """Context manager for timing operations."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.metrics.record_timing(operation, duration)

    def _generate_signature(self, params: dict, timestamp: str) -> str:
        """Forge an HMAC SHA256 signature for the API's sacred gate."""
        # Ensure params are sorted for consistent signature generation
        sorted_params = json.dumps(params, separators=(",", ":"), sort_keys=True)
        param_str = timestamp + self.api_key + "5000" + sorted_params
        return hmac.new(
            self.api_secret.encode("utf-8"), param_str.encode("utf-8"), hashlib.sha256,
        ).hexdigest()

    def _generate_signature_get(self, query_string: str, timestamp: str) -> str:
        """Forge an HMAC SHA256 signature for GET requests."""
        param_str = timestamp + self.api_key + "5000" + query_string
        return hmac.new(
            self.api_secret.encode("utf-8"), param_str.encode("utf-8"), hashlib.sha256,
        ).hexdigest()

    def _send_request(
        self, method: str, endpoint: str, params: dict = None, retries: int = None,
    ) -> dict:
        """Cast an HTTP spell to commune with Bybit's API with enhanced error handling and monitoring.

        Args:
            method (str): HTTP method (GET/POST).
            endpoint (str): API endpoint path.
            params (Dict): Request parameters.
            retries (int): Number of retry attempts.

        Returns:
            Dict: API response result or empty dict on failure.

        """
        if params is None:
            params = {}
        if retries is None:
            retries = self.retry_attempts

        if not self.rate_limiter.wait_for_tokens():
            logger.warning("Rate limit exceeded, request rejected")
            self.metrics.record_error("rate_limit_exceeded")
            return {}

        with self._timing_context(f"api_request_{endpoint}"):
            return self._execute_request_with_circuit_breaker(
                method, endpoint, params, retries,
            )

    def _execute_request_with_circuit_breaker(
        self, method: str, endpoint: str, params: dict, retries: int,
    ) -> dict:
        """Execute request with circuit breaker protection."""
        try:
            return self.circuit_breaker.call(
                self._execute_request, method, endpoint, params, retries,
            )
        except Exception as e:
            logger.error(f"Circuit breaker prevented request to {endpoint}: {e!s}")
            self.metrics.record_error("circuit_breaker_open")
            return {}

    def _execute_request(
        self, method: str, endpoint: str, params: dict, retries: int,
    ) -> dict:
        """Execute the actual HTTP request with retry logic."""
        last_exception = None

        for attempt in range(retries):
            try:
                timestamp = str(int(time.time() * 1000))
                headers = {
                    "X-BAPI-API-KEY": self.api_key,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-RECV-WINDOW": "5000",
                    "Content-Type": "application/json",
                    "User-Agent": "BybitV5Wizard/2.0",
                }

                if method == "POST":
                    signature = self._generate_signature(params, timestamp)
                    headers["X-BAPI-SIGN"] = signature
                elif method == "GET":
                    sorted_params = "&".join(
                        [f"{k}={v}" for k, v in sorted(params.items())],
                    )
                    signature = self._generate_signature_get(sorted_params, timestamp)
                    headers["X-BAPI-SIGN"] = signature
                else:
                    raise ValueError(f"Invalid HTTP method: {method}")

                url = f"{self.base_url}{endpoint}"

                if method == "GET":
                    response = self.session.get(
                        url, headers=headers, params=params, timeout=30,
                    )
                elif method == "POST":
                    response = self.session.post(
                        url, headers=headers, json=params, timeout=30,
                    )

                response.raise_for_status()
                result = response.json()

                if not isinstance(result, dict):
                    raise ValueError("Invalid response format")

                self.metrics.increment("api_requests_success")
                logger.debug(f"Request successful: {method} {endpoint}")

                if result.get("retCode") == 0:
                    self.connection_health["api"] = True
                    print(
                        Fore.GREEN
                        + f"# Spell cast successfully: {endpoint}"
                        + Style.RESET_ALL,
                    )
                    return result.get("result", {})
                error_msg = result.get("retMsg", "Unknown API error")
                logger.error(f"API error: {error_msg} for endpoint {endpoint}")
                self.metrics.record_error("api_error")
                print(Fore.RED + f"# Spell failed: {error_msg}" + Style.RESET_ALL)
                return {}

            except requests.exceptions.Timeout as e:
                last_exception = e
                logger.warning(
                    f"Request timeout for {endpoint} (attempt {attempt + 1}/{retries})",
                )
                self.metrics.record_error("request_timeout")

            except requests.exceptions.ConnectionError as e:
                last_exception = e
                logger.warning(
                    f"Connection error for {endpoint} (attempt {attempt + 1}/{retries})",
                )
                self.metrics.record_error("connection_error")
                self.connection_health["api"] = False

            except requests.exceptions.HTTPError as e:
                last_exception = e
                logger.warning(
                    f"HTTP error {e.response.status_code} for {endpoint} (attempt {attempt + 1}/{retries})",
                )
                self.metrics.record_error(f"http_error_{e.response.status_code}")

                # Don't retry on client errors (4xx)
                if 400 <= e.response.status_code < 500:
                    break

            except Exception as e:
                last_exception = e
                logger.error(f"Unexpected error for {endpoint}: {e!s}")
                self.metrics.record_error("unexpected_error")

            if attempt < retries - 1:
                delay = min(self.retry_delay * (2**attempt), self.max_retry_delay)
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)

        # All retries exhausted
        logger.error(
            f"All retry attempts exhausted for {endpoint}. Last error: {last_exception!s}",
        )
        self.metrics.record_error("all_retries_exhausted")
        return {}

    # --- Market Data Endpoints ---

    def get_kline(
        self,
        category: str,
        symbol: str,
        interval: str,
        start: int | None = None,
        end: int | None = None,
        limit: int = 200,
    ) -> dict:
        """Retrieve kline/candlestick data with enhanced error handling.

        Endpoint: GET /v5/market/kline
        """
        endpoint = "/v5/market/kline"
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        logger.info(f"Fetching kline data for {symbol} ({interval})")
        print(
            Fore.CYAN
            + f"# Conjuring kline data for {symbol} ({interval})..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_mark_price_kline(
        self,
        category: str,
        symbol: str,
        interval: str,
        start: int | None = None,
        end: int | None = None,
        limit: int = 200,
    ) -> dict:
        """Retrieve mark price kline data.

        Endpoint: GET /v5/market/mark-price-kline
        """
        endpoint = "/v5/market/mark-price-kline"
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        print(
            Fore.CYAN
            + f"# Fetching mark price kline for {symbol} ({interval})..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_index_price_kline(
        self,
        category: str,
        symbol: str,
        interval: str,
        start: int | None = None,
        end: int | None = None,
        limit: int = 200,
    ) -> dict:
        """Retrieve index price kline data.

        Endpoint: GET /v5/market/index-price-kline
        """
        endpoint = "/v5/market/index-price-kline"
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        print(
            Fore.CYAN
            + f"# Fetching index price kline for {symbol} ({interval})..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_premium_index_price_kline(
        self,
        category: str,
        symbol: str,
        interval: str,
        start: int | None = None,
        end: int | None = None,
        limit: int = 200,
    ) -> dict:
        """Retrieve premium index price kline data.

        Endpoint: GET /v5/market/premium-index-price-kline
        """
        endpoint = "/v5/market/premium-index-price-kline"
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        print(
            Fore.CYAN
            + f"# Fetching premium index price kline for {symbol} ({interval})..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_instruments_info(
        self,
        category: str,
        symbol: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> dict:
        """Retrieve instrument information.

        Endpoint: GET /v5/market/instruments-info
        """
        endpoint = "/v5/market/instruments-info"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        if status:
            params["status"] = status
        if limit:
            params["limit"] = limit
        print(
            Fore.CYAN
            + f"# Fetching instruments info for {category}..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_orderbook(self, category: str, symbol: str, limit: int = 50) -> dict:
        """Retrieve order book data.

        Endpoint: GET /v5/market/orderbook
        """
        endpoint = "/v5/market/orderbook"
        params = {"category": category, "symbol": symbol, "limit": limit}
        print(Fore.CYAN + f"# Fetching order book for {symbol}..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_tickers(
        self,
        category: str,
        symbol: str | None = None,
        base_coin: str | None = None,
        exp_date: str | None = None,
    ) -> dict:
        """Retrieve ticker information.

        Endpoint: GET /v5/market/tickers
        """
        endpoint = "/v5/market/tickers"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        if base_coin:
            params["baseCoin"] = base_coin
        if exp_date:
            params["expDate"] = exp_date
        print(Fore.CYAN + f"# Fetching tickers for {category}..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_funding_rate(self, category: str, symbol: str) -> dict:
        """Retrieve funding rate history.

        Endpoint: GET /v5/market/funding/history
        """
        endpoint = "/v5/market/funding/history"
        params = {"category": category, "symbol": symbol}
        print(Fore.CYAN + f"# Fetching funding rate for {symbol}..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_public_trade(
        self,
        category: str,
        symbol: str,
        base_coin: str | None = None,
        option_type: str | None = None,
        limit: int = 500,
    ) -> dict:
        """Retrieve recent public trades.

        Endpoint: GET /v5/market/recent-trade
        """
        endpoint = "/v5/market/recent-trade"
        params = {"category": category, "symbol": symbol, "limit": limit}
        if base_coin:
            params["baseCoin"] = base_coin
        if option_type:
            params["optionType"] = option_type
        print(Fore.CYAN + f"# Fetching recent trades for {symbol}..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_open_interest(
        self,
        category: str,
        symbol: str,
        interval: str = "5min",
        start: int | None = None,
        end: int | None = None,
        limit: int = 200,
    ) -> dict:
        """Retrieve open interest data.

        Endpoint: GET /v5/market/open-interest
        """
        endpoint = "/v5/market/open-interest"
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        print(Fore.CYAN + f"# Fetching open interest for {symbol}..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_historical_volatility(
        self,
        category: str = "option",
        base_coin: str | None = None,
        period: int | None = None,
    ) -> dict:
        """Retrieve historical volatility data.

        Endpoint: GET /v5/market/historical-volatility
        """
        endpoint = "/v5/market/historical-volatility"
        params = {"category": category}
        if base_coin:
            params["baseCoin"] = base_coin
        if period:
            params["period"] = period
        print(
            Fore.CYAN
            + f"# Fetching historical volatility for {category}..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_insurance(self, coin: str | None = None) -> dict:
        """Retrieve insurance fund data.

        Endpoint: GET /v5/market/insurance
        """
        endpoint = "/v5/market/insurance"
        params = {}
        if coin:
            params["coin"] = coin
        print(Fore.CYAN + "# Fetching insurance fund data..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_risk_limit(self, category: str, symbol: str | None = None) -> dict:
        """Retrieve risk limit data.

        Endpoint: GET /v5/market/risk-limit
        """
        endpoint = "/v5/market/risk-limit"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        print(Fore.CYAN + f"# Fetching risk limit for {category}..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_delivery_price(
        self,
        category: str,
        symbol: str | None = None,
        base_coin: str | None = None,
        limit: int = 200,
    ) -> dict:
        """Retrieve delivery price data.

        Endpoint: GET /v5/market/delivery-price
        """
        endpoint = "/v5/market/delivery-price"
        params = {"category": category, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        if base_coin:
            params["baseCoin"] = base_coin
        print(
            Fore.CYAN + f"# Fetching delivery price for {category}..." + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_server_time(self) -> dict:
        """Retrieve server time.

        Endpoint: GET /v5/market/time
        """
        endpoint = "/v5/market/time"
        print(Fore.CYAN + "# Fetching server time..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, {})

    def get_long_short_ratio(
        self, category: str, symbol: str, period: str, limit: int = 50,
    ) -> dict:
        """Retrieve long-short ratio data.

        Endpoint: GET /v5/market/long-short-ratio
        """
        endpoint = "/v5/market/long-short-ratio"
        params = {
            "category": category,
            "symbol": symbol,
            "period": period,
            "limit": limit,
        }
        print(
            Fore.CYAN
            + f"# Fetching long-short ratio for {symbol} ({period})..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_top_long_short_account_ratio(
        self, category: str, symbol: str, period: str, limit: int = 50,
    ) -> dict:
        """Retrieve top long-short account ratio data.

        Endpoint: GET /v5/market/top-long-short-account-ratio
        """
        endpoint = "/v5/market/top-long-short-account-ratio"
        params = {
            "category": category,
            "symbol": symbol,
            "period": period,
            "limit": limit,
        }
        print(
            Fore.CYAN
            + f"# Fetching top long-short account ratio for {symbol} ({period})..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_top_long_short_position_ratio(
        self, category: str, symbol: str, period: str, limit: int = 50,
    ) -> dict:
        """Retrieve top long-short position ratio data.

        Endpoint: GET /v5/market/top-long-short-position-ratio
        """
        endpoint = "/v5/market/top-long-short-position-ratio"
        params = {
            "category": category,
            "symbol": symbol,
            "period": period,
            "limit": limit,
        }
        print(
            Fore.CYAN
            + f"# Fetching top long-short position ratio for {symbol} ({period})..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_taker_buy_sell_ratio(
        self, category: str, symbol: str, period: str, limit: int = 50,
    ) -> dict:
        """Retrieve taker buy-sell ratio data.

        Endpoint: GET /v5/market/taker-buy-sell-ratio
        """
        endpoint = "/v5/market/taker-buy-sell-ratio"
        params = {
            "category": category,
            "symbol": symbol,
            "period": period,
            "limit": limit,
        }
        print(
            Fore.CYAN
            + f"# Fetching taker buy-sell ratio for {symbol} ({period})..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    # --- Trade Endpoints ---

    def place_market_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        category: str = "linear",
        break_even: bool = False,
        tsl: bool = False,
        tsl_distance: float | None = None,
        profit_target: float | None = None,
    ) -> dict:
        """Summon a market order with optional enchantments and enhanced tracking.

        Endpoint: POST /v5/order/create
        """
        endpoint = "/v5/order/create"
        params = {
            "category": category,
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": "Market",
            "qty": str(qty),
        }

        logger.info(f"Placing market order: {symbol} {side} {qty}")
        print(
            Fore.CYAN
            + f"# Casting market order for {symbol} ({side})..."
            + Style.RESET_ALL,
        )

        result = self._send_request("POST", endpoint, params)

        if result and (break_even or tsl or profit_target):
            self.positions[symbol] = Position(
                symbol=symbol,
                break_even_enabled=break_even,
                tsl_enabled=tsl,
                tsl_distance=tsl_distance,
                profit_target=profit_target,
                profit_action="partial_close",
                close_percentage=50,
                side=side,
            )
            logger.info(f"Position tracking enabled for {symbol}")

        if result:
            self.metrics.increment("orders_placed")

        return result

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        category: str = "linear",
        break_even: bool = False,
        tsl: bool = False,
        tsl_distance: float | None = None,
        profit_target: float | None = None,
    ) -> dict:
        """Forge a limit order with precision and optional enchantments.

        Endpoint: POST /v5/order/create
        """
        endpoint = "/v5/order/create"
        params = {
            "category": category,
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": "Limit",
            "qty": str(qty),
            "price": str(price),
        }
        print(
            Fore.CYAN
            + f"# Forging limit order for {symbol} at {price}..."
            + Style.RESET_ALL,
        )
        result = self._send_request("POST", endpoint, params)
        if result and (break_even or tsl or profit_target):
            self.positions[symbol] = {
                "entry_price": None,
                "break_even_enabled": break_even,
                "tsl_enabled": tsl,
                "tsl_distance": tsl_distance,
                "profit_target": profit_target,
                "profit_action": "partial_close",
                "close_percentage": 50,
            }
        return result

    def place_conditional_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        trigger_price: float,
        order_type: str = "Limit",
        price: float | None = None,
        category: str = "linear",
    ) -> dict:
        """Invoke a conditional order, triggered by the market's pulse.

        Endpoint: POST /v5/order/create
        """
        endpoint = "/v5/order/create"
        params = {
            "category": category,
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": order_type,
            "qty": str(qty),
            "triggerPrice": str(trigger_price),
            "triggerDirection": 1 if side.lower() == "buy" else 2,
        }
        if price:
            params["price"] = str(price)
        print(
            Fore.CYAN
            + f"# Summoning conditional order for {symbol} at trigger {trigger_price}..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def place_tpsl_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        take_profit: float | None = None,
        stop_loss: float | None = None,
        category: str = "linear",
    ) -> dict:
        """Enchant an order with take-profit and stop-loss wards.

        Endpoint: POST /v5/order/create
        """
        endpoint = "/v5/order/create"
        params = {
            "category": category,
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": "Market",
            "qty": str(qty),
        }
        if take_profit:
            params["takeProfit"] = str(take_profit)
        if stop_loss:
            params["stopLoss"] = str(stop_loss)
        print(
            Fore.CYAN + f"# Enchanting {symbol} order with TP/SL..." + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def place_batch_orders(self, orders: list[dict], category: str) -> dict:
        """Unleash a flurry of orders in a single incantation.

        Endpoint: POST /v5/order/create-batch
        """
        endpoint = "/v5/order/create-batch"
        params = {
            "category": category,
            "request": [
                {
                    "symbol": order["symbol"],
                    "side": order["side"].capitalize(),
                    "orderType": order.get("orderType", "Market"),
                    "qty": str(order["qty"]),
                    **({"price": str(order["price"])} if order.get("price") else {}),
                    **(
                        {"takeProfit": str(order["takeProfit"])}
                        if order.get("takeProfit")
                        else {}
                    ),
                    **(
                        {"stopLoss": str(order["stopLoss"])}
                        if order.get("stopLoss")
                        else {}
                    ),
                }
                for order in orders
            ],
        }
        print(
            Fore.CYAN
            + f"# Casting {len(orders)} batch orders for {category}..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def amend_order(
        self,
        symbol: str,
        category: str = "linear",
        order_id: str | None = None,
        order_link_id: str | None = None,
        qty: float | None = None,
        price: float | None = None,
        trigger_price: float | None = None,
    ) -> dict:
        """Amend an existing order.

        Endpoint: POST /v5/order/amend
        """
        endpoint = "/v5/order/amend"
        params = {"category": category, "symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        if order_link_id:
            params["orderLinkId"] = order_link_id
        if qty:
            params["qty"] = str(qty)
        if price:
            params["price"] = str(price)
        if trigger_price:
            params["triggerPrice"] = str(trigger_price)
        print(Fore.CYAN + f"# Amending order for {symbol}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    def amend_batch_orders(self, orders: list[dict], category: str) -> dict:
        """Amend multiple orders in a single incantation.

        Endpoint: POST /v5/order/amend-batch
        """
        endpoint = "/v5/order/amend-batch"
        params = {
            "category": category,
            "request": [
                {
                    "symbol": order["symbol"],
                    "orderId": order.get("orderId"),
                    **(
                        {"orderLinkId": order["orderLinkId"]}
                        if order.get("orderLinkId")
                        else {}
                    ),
                    **({"qty": str(order["qty"])} if order.get("qty") else {}),
                    **({"price": str(order["price"])} if order.get("price") else {}),
                    **(
                        {"triggerPrice": str(order["triggerPrice"])}
                        if order.get("triggerPrice")
                        else {}
                    ),
                }
                for order in orders
            ],
        }
        print(
            Fore.CYAN
            + f"# Amending {len(orders)} batch orders for {category}..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def cancel_order(
        self,
        symbol: str,
        category: str = "linear",
        order_id: str | None = None,
        order_link_id: str | None = None,
    ) -> dict:
        """Banish an order back to the void.

        Endpoint: POST /v5/order/cancel
        """
        endpoint = "/v5/order/cancel"
        params = {"category": category, "symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        if order_link_id:
            params["orderLinkId"] = order_link_id
        print(Fore.CYAN + f"# Banishing order for {symbol}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    def cancel_all_orders(
        self, category: str = "linear", symbol: str | None = None,
    ) -> dict:
        """Obliterate all orders in a cataclysmic sweep.

        Endpoint: POST /v5/order/cancel-all
        """
        endpoint = "/v5/order/cancel-all"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        print(Fore.CYAN + f"# Obliterating all {category} orders..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    def close_position(
        self,
        symbol: str,
        category: str = "linear",
        order_type: str = "Market",
        price: float | None = None,
    ) -> dict:
        """Close a position with market or limit order.

        Endpoint: POST /v5/order/create
        """
        endpoint = "/v5/order/create"
        position_list = self.get_positions(category, symbol).get("list", [])
        if not position_list:
            print(Fore.RED + f"# No position found for {symbol}!" + Style.RESET_ALL)
            return {}

        pos = position_list[0]
        side = "Sell" if pos["side"] == "Buy" else "Buy"
        qty = float(pos["size"])  # Ensure qty is float for calculations

        params = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),
        }
        if price and order_type == "Limit":
            params["price"] = str(price)
        print(
            Fore.CYAN + f"# Closing position for {symbol} ({side})..." + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def get_open_orders(
        self, category: str = "linear", symbol: str | None = None,
    ) -> dict:
        """Reveal the active orders lingering in the ether.

        Endpoint: GET /v5/order/realtime
        """
        endpoint = "/v5/order/realtime"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        print(Fore.CYAN + f"# Unveiling open {category} orders..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_order_history(
        self, category: str = "linear", symbol: str | None = None, limit: int = 50,
    ) -> dict:
        """Seek the chronicles of past trades.

        Endpoint: GET /v5/order/history
        """
        endpoint = "/v5/order/history"
        params = {"category": category, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        print(
            Fore.CYAN + f"# Seeking order history for {category}..." + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_transaction_log(
        self, category: str = "linear", symbol: str | None = None,
    ) -> dict:
        """Retrieve transaction logs.

        Endpoint: GET /v5/order/transaction-log
        """
        endpoint = "/v5/order/transaction-log"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        print(
            Fore.CYAN
            + f"# Retrieving transaction logs for {category}..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    # --- Position Endpoints ---

    def get_positions(
        self, category: str = "linear", symbol: str | None = None,
    ) -> dict:
        """Summon the spirits of your active positions.

        Endpoint: GET /v5/position/list
        """
        endpoint = "/v5/position/list"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        print(Fore.CYAN + f"# Summoning {category} positions..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def set_leverage(
        self,
        symbol: str,
        buy_leverage: float,
        sell_leverage: float,
        category: str = "linear",
    ) -> dict:
        """Adjust the leverage, bending the market's force.

        Endpoint: POST /v5/position/set-leverage
        """
        endpoint = "/v5/position/set-leverage"
        params = {
            "category": category,
            "symbol": symbol,
            "buyLeverage": str(buy_leverage),
            "sellLeverage": str(sell_leverage),
        }
        print(
            Fore.CYAN
            + f"# Bending leverage for {symbol} to {buy_leverage}x..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def set_trading_stop(
        self,
        symbol: str,
        category: str = "linear",
        take_profit: float | None = None,
        stop_loss: float | None = None,
        trailing_stop: float | None = None,
        active_price: float | None = None,
        tpsl_mode: str = "Full",
    ) -> dict:
        """Enchant a position with protective TP/SL or TSL wards.

        Endpoint: POST /v5/position/set-trading-stop
        """
        endpoint = "/v5/position/set-trading-stop"
        params = {"category": category, "symbol": symbol, "tpslMode": tpsl_mode}
        if take_profit:
            params["takeProfit"] = str(take_profit)
        if stop_loss:
            params["stopLoss"] = str(stop_loss)
        if trailing_stop:
            params["trailingStop"] = str(trailing_stop)
        if active_price:
            params["activePrice"] = str(active_price)
        print(
            Fore.CYAN
            + f"# Enchanting {symbol} with TP/SL/TSL wards..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def set_risk_limit(self, category: str, symbol: str, risk_id: int) -> dict:
        """Set the risk limit for a position.

        Endpoint: POST /v5/position/set-risk-limit
        """
        endpoint = "/v5/position/set-risk-limit"
        params = {"category": category, "symbol": symbol, "riskId": risk_id}
        print(Fore.CYAN + f"# Setting risk limit for {symbol}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    def switch_position_mode(self, category: str, symbol: str, mode: int) -> dict:
        """Switch position mode (One-Way or Hedge).

        Endpoint: POST /v5/position/switch-mode
        """
        endpoint = "/v5/position/switch-mode"
        params = {"category": category, "symbol": symbol, "mode": mode}
        print(
            Fore.CYAN
            + f"# Switching position mode for {symbol} to {mode}..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def set_tpsl_mode(self, category: str, symbol: str, tpsl_mode: str) -> dict:
        """Set TP/SL mode (Full or Partial).

        Endpoint: POST /v5/position/set-tpsl-mode
        """
        endpoint = "/v5/position/set-tpsl-mode"
        params = {"category": category, "symbol": symbol, "tpslMode": tpsl_mode}
        print(
            Fore.CYAN
            + f"# Setting TP/SL mode for {symbol} to {tpsl_mode}..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def set_auto_add_margin(self, category: str, symbol: str, is_auto: bool) -> dict:
        """Set auto add margin feature for Isolated margin mode.

        Endpoint: POST /v5/position/set-auto-add-margin
        """
        endpoint = "/v5/position/set-auto-add-margin"
        params = {
            "category": category,
            "symbol": symbol,
            "autoAddMargin": 1 if is_auto else 0,
        }
        print(
            Fore.CYAN
            + f"# {'Enabling' if is_auto else 'Disabling'} auto add margin for {symbol}..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def get_closed_pnl(
        self, category: str, symbol: str | None = None, limit: int = 50,
    ) -> dict:
        """Retrieve closed PNL records.

        Endpoint: GET /v5/position/closed-pnl
        """
        endpoint = "/v5/position/closed-pnl"
        params = {"category": category, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        print(
            Fore.CYAN + f"# Retrieving closed PNL for {category}..." + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def add_margin(
        self, category: str, symbol: str, margin: float, position_idx: int | None = None,
    ) -> dict:
        """Add margin to a position.

        Endpoint: POST /v5/position/add-margin
        """
        endpoint = "/v5/position/add-margin"
        params = {"category": category, "symbol": symbol, "margin": str(margin)}
        if position_idx is not None:
            params["positionIdx"] = position_idx
        print(Fore.CYAN + f"# Adding {margin} margin to {symbol}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    # --- Account Endpoints ---

    def get_wallet_balance(
        self, account_type: str = "UNIFIED", coin: str | None = None,
    ) -> dict:
        """Retrieve account wallet balance with enhanced caching.

        Endpoint: GET /v5/account/wallet-balance
        """
        endpoint = "/v5/account/wallet-balance"
        params = {"accountType": account_type}
        if coin:
            params["coin"] = coin

        logger.info(f"Fetching wallet balance for {account_type} account")
        print(
            Fore.CYAN
            + f"# Unveiling wallet balance for {account_type} account..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_account_info(self) -> dict:
        """Retrieve account information.

        Endpoint: GET /v5/account/info
        """
        endpoint = "/v5/account/info"
        print(Fore.CYAN + "# Accessing account information..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, {})

    def get_fee_rate(self, category: str, symbol: str | None = None) -> dict:
        """Retrieve trading fee rate.

        Endpoint: GET /v5/account/fee-rate
        """
        endpoint = "/v5/account/fee-rate"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        print(Fore.CYAN + f"# Fetching fee rate for {category}..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_coin_greeks(
        self,
        category: str = "option",
        base_coin: str | None = None,
        symbol: str | None = None,
    ) -> dict:
        """Retrieve Coin-Greeks data.

        Endpoint: GET /v5/account/get-coin-greeks
        """
        endpoint = "/v5/account/get-coin-greeks"
        params = {"category": category}
        if base_coin:
            params["baseCoin"] = base_coin
        if symbol:
            params["symbol"] = symbol
        print(Fore.CYAN + "# Fetching Coin-Greeks data..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_account_transaction_log(
        self,
        account_type: str,
        category: str | None = None,
        coin: str | None = None,
        limit: int = 50,
    ) -> dict:
        """Retrieve account transaction logs.

        Endpoint: GET /v5/account/transaction-log
        """
        endpoint = "/v5/account/transaction-log"
        params = {"accountType": account_type, "limit": limit}
        if category:
            params["category"] = category
        if coin:
            params["coin"] = coin
        print(
            Fore.CYAN
            + f"# Retrieving account transaction logs for {account_type}..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_borrow_history(
        self, category: str, coin: str | None = None, limit: int = 50,
    ) -> dict:
        """Retrieve borrow history.

        Endpoint: GET /v5/account/borrow-history
        """
        endpoint = "/v5/account/borrow-history"
        params = {"category": category, "limit": limit}
        if coin:
            params["coin"] = coin
        print(
            Fore.CYAN
            + f"# Retrieving borrow history for {category}..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_mmp_state(self, category: str, symbol: str) -> dict:
        """Retrieve Market Maker Protection (MMP) state.

        Endpoint: GET /v5/account/mmp-state
        """
        endpoint = "/v5/account/mmp-state"
        params = {"category": category, "symbol": symbol}
        print(Fore.CYAN + f"# Retrieving MMP state for {symbol}..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def set_margin_mode(self, category: str, symbol: str, margin_mode: str) -> dict:
        """Set margin mode for a symbol (Isolated or Cross).

        Endpoint: POST /v5/account/set-margin-mode
        """
        endpoint = "/v5/account/set-margin-mode"
        params = {"category": category, "symbol": symbol, "marginMode": margin_mode}
        print(
            Fore.CYAN
            + f"# Setting margin mode for {symbol} to {margin_mode}..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def set_mmp(
        self,
        category: str,
        symbol: str,
        window_ms: int,
        frozen_period_ms: int,
        qty_limit: float,
        delta_limit: float,
    ) -> dict:
        """Set Market Maker Protection (MMP) parameters.

        Endpoint: POST /v5/account/set-mmp
        """
        endpoint = "/v5/account/set-mmp"
        params = {
            "category": category,
            "symbol": symbol,
            "windowMs": window_ms,
            "frozenPeriodMs": frozen_period_ms,
            "qtyLimit": str(qty_limit),
            "deltaLimit": str(delta_limit),
        }
        print(Fore.CYAN + f"# Setting MMP for {symbol}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    def reset_mmp(self, category: str, symbol: str) -> dict:
        """Reset Market Maker Protection (MMP) for a symbol.

        Endpoint: POST /v5/account/reset-mmp
        """
        endpoint = "/v5/account/reset-mmp"
        params = {"category": category, "symbol": symbol}
        print(Fore.CYAN + f"# Resetting MMP for {symbol}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    def get_margin_mode_info(self, category: str, symbol: str | None = None) -> dict:
        """Retrieve margin mode information.

        Endpoint: GET /v5/account/margin-mode-info
        """
        endpoint = "/v5/account/margin-mode-info"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        print(
            Fore.CYAN
            + f"# Retrieving margin mode info for {category}..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    # --- Asset Endpoints ---

    def get_deposit_records(self, coin: str | None = None, limit: int = 50) -> dict:
        """Retrieve deposit records.

        Endpoint: GET /v5/asset/deposit/query-deposit-records
        """
        endpoint = "/v5/asset/deposit/query-deposit-records"
        params = {"limit": limit}
        if coin:
            params["coin"] = coin
        print(Fore.CYAN + "# Retrieving deposit records..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_withdrawal_records(self, coin: str | None = None, limit: int = 50) -> dict:
        """Retrieve withdrawal records.

        Endpoint: GET /v5/asset/withdraw/query-withdraw-records
        """
        endpoint = "/v5/asset/withdraw/query-withdraw-records"
        params = {"limit": limit}
        if coin:
            params["coin"] = coin
        print(Fore.CYAN + "# Retrieving withdrawal records..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_all_coins_info(self, coin: str | None = None) -> dict:
        """Retrieve information of all coins.

        Endpoint: GET /v5/asset/coin/query-info
        """
        endpoint = "/v5/asset/coin/query-info"
        params = {}
        if coin:
            params["coin"] = coin
        print(Fore.CYAN + "# Retrieving information for all coins..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_asset_transfer_records(
        self, transfer_id: str | None = None, limit: int = 50,
    ) -> dict:
        """Retrieve asset transfer records.

        Endpoint: GET /v5/asset/transfer/query-transfer-list
        """
        endpoint = "/v5/asset/transfer/query-transfer-list"
        params = {"limit": limit}
        if transfer_id:
            params["transferId"] = transfer_id
        print(Fore.CYAN + "# Retrieving asset transfer records..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def transfer_asset(
        self,
        transfer_id: str,
        coin: str,
        amount: float,
        from_account_type: str,
        to_account_type: str,
    ) -> dict:
        """Transfer asset between accounts.

        Endpoint: POST /v5/asset/transfer/inter-transfer
        """
        endpoint = "/v5/asset/transfer/inter-transfer"
        params = {
            "transferId": transfer_id,
            "coin": coin,
            "amount": str(amount),
            "fromAccountType": from_account_type,
            "toAccountType": to_account_type,
        }
        print(
            Fore.CYAN
            + f"# Transferring {amount} {coin} from {from_account_type} to {to_account_type}..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def withdrawal(
        self, coin: str, chain: str, address: str, amount: float, tag: str | None = None,
    ) -> dict:
        """Withdraw an asset.

        Endpoint: POST /v5/asset/withdraw/create
        """
        endpoint = "/v5/asset/withdraw/create"
        params = {
            "coin": coin,
            "chain": chain,
            "address": address,
            "amount": str(amount),
        }
        if tag:
            params["tag"] = tag
        print(
            Fore.CYAN
            + f"# Initiating withdrawal of {amount} {coin} to {address}..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def get_internal_deposit_records(
        self, coin: str | None = None, limit: int = 50,
    ) -> dict:
        """Retrieve internal deposit records.

        Endpoint: GET /v5/asset/deposit/query-internal-deposit-records
        """
        endpoint = "/v5/asset/deposit/query-internal-deposit-records"
        params = {"limit": limit}
        if coin:
            params["coin"] = coin
        print(Fore.CYAN + "# Retrieving internal deposit records..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_sub_member_deposit_records(
        self, coin: str | None = None, limit: int = 50,
    ) -> dict:
        """Retrieve sub-member deposit records.

        Endpoint: GET /v5/asset/deposit/query-sub-member-deposit-records
        """
        endpoint = "/v5/asset/deposit/query-sub-member-deposit-records"
        params = {"limit": limit}
        if coin:
            params["coin"] = coin
        print(
            Fore.CYAN + "# Retrieving sub-member deposit records..." + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_deposit_address(self, coin: str, chain: str | None = None) -> dict:
        """Retrieve deposit address.

        Endpoint: GET /v5/asset/deposit/query-deposit-address
        """
        endpoint = "/v5/asset/deposit/query-deposit-address"
        params = {"coin": coin}
        if chain:
            params["chain"] = chain
        print(
            Fore.CYAN + f"# Retrieving deposit address for {coin}..." + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_universal_transfer_list(
        self, transfer_id: str | None = None, limit: int = 50,
    ) -> dict:
        """Retrieve universal transfer records.

        Endpoint: GET /v5/asset/transfer/query-universal-transfer-list
        """
        endpoint = "/v5/asset/transfer/query-universal-transfer-list"
        params = {"limit": limit}
        if transfer_id:
            params["transferId"] = transfer_id
        print(
            Fore.CYAN + "# Retrieving universal transfer records..." + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_account_coins_balance(
        self, account_type: str, coin: str | None = None,
    ) -> dict:
        """Retrieve account coins balance.

        Endpoint: GET /v5/asset/transfer/query-account-coins-balance
        """
        endpoint = "/v5/asset/transfer/query-account-coins-balance"
        params = {"accountType": account_type}
        if coin:
            params["coin"] = coin
        print(
            Fore.CYAN
            + f"# Retrieving account coins balance for {account_type}..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def universal_transfer(
        self,
        transfer_id: str,
        coin: str,
        amount: float,
        from_member_id: str,
        to_member_id: str,
        from_account_type: str,
        to_account_type: str,
    ) -> dict:
        """Perform a universal transfer.

        Endpoint: POST /v5/asset/transfer/universal-transfer
        """
        endpoint = "/v5/asset/transfer/universal-transfer"
        params = {
            "transferId": transfer_id,
            "coin": coin,
            "amount": str(amount),
            "fromMemberId": from_member_id,
            "toMemberId": to_member_id,
            "fromAccountType": from_account_type,
            "toAccountType": to_account_type,
        }
        print(
            Fore.CYAN
            + f"# Performing universal transfer of {amount} {coin}..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def get_asset_info(self, account_type: str, coin: str | None = None) -> dict:
        """Retrieve asset information.

        Endpoint: GET /v5/asset/transfer/query-asset-info
        """
        endpoint = "/v5/asset/transfer/query-asset-info"
        params = {"accountType": account_type}
        if coin:
            params["coin"] = coin
        print(
            Fore.CYAN
            + f"# Retrieving asset info for {account_type}..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_transfer_coin_list(self, coin: str | None = None) -> dict:
        """Retrieve transfer coin list.

        Endpoint: GET /v5/asset/transfer/query-transfer-coin-list
        """
        endpoint = "/v5/asset/transfer/query-transfer-coin-list"
        params = {}
        if coin:
            params["coin"] = coin
        print(Fore.CYAN + "# Retrieving transfer coin list..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def save_transfer_id(self, transfer_id: str) -> dict:
        """Save a transfer ID.

        Endpoint: POST /v5/asset/transfer/save-transfer-id
        """
        endpoint = "/v5/asset/transfer/save-transfer-id"
        params = {"transferId": transfer_id}
        print(Fore.CYAN + f"# Saving transfer ID {transfer_id}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    def get_withdrawable_amount(self, coin: str) -> dict:
        """Retrieve withdrawable amount.

        Endpoint: GET /v5/asset/withdraw/withdrawable-amount
        """
        endpoint = "/v5/asset/withdraw/withdrawable-amount"
        params = {"coin": coin}
        print(
            Fore.CYAN
            + f"# Retrieving withdrawable amount for {coin}..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    # --- User Endpoints ---

    def get_api_key_info(self) -> dict:
        """Retrieve API key information.

        Endpoint: GET /v5/user/query-api
        """
        endpoint = "/v5/user/query-api"
        print(Fore.CYAN + "# Retrieving API key info..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, {})

    def get_sub_member(self, member_id: str | None = None) -> dict:
        """Retrieve sub-member information.

        Endpoint: GET /v5/user/sub-member
        """
        endpoint = "/v5/user/sub-member"
        params = {}
        if member_id:
            params["memberId"] = member_id
        print(Fore.CYAN + "# Retrieving sub-member info..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_member_type(self) -> dict:
        """Retrieve member type information.

        Endpoint: GET /v5/user/member-type
        """
        endpoint = "/v5/user/member-type"
        print(Fore.CYAN + "# Retrieving member type info..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, {})

    def toggle_loan_union_interest_repay(self, status: int) -> dict:
        """Toggle loan union interest repay.

        Endpoint: GET /v5/user/loan-union/toggle-interest-repay
        """
        endpoint = "/v5/user/loan-union/toggle-interest-repay"
        params = {"status": status}
        print(
            Fore.CYAN
            + f"# Toggling loan union interest repay to {status}..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_loan_union_interest_repay_status(self) -> dict:
        """Retrieve loan union interest repay status.

        Endpoint: GET /v5/user/loan-union/interest-repay-status
        """
        endpoint = "/v5/user/loan-union/interest-repay-status"
        print(
            Fore.CYAN
            + "# Retrieving loan union interest repay status..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, {})

    def create_sub_member(self, username: str, password: str, member_type: str) -> dict:
        """Create a new sub-member.

        Endpoint: POST /v5/user/create-sub-member
        """
        endpoint = "/v5/user/create-sub-member"
        params = {"username": username, "password": password, "memberType": member_type}
        print(Fore.CYAN + f"# Creating sub-member {username}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    def create_api_key(
        self,
        api_key_name: str,
        read_only: int,
        ips: str | None = None,
        permissions: list[str] | None = None,
    ) -> dict:
        """Create a new API key.

        Endpoint: POST /v5/user/create-api-key
        """
        endpoint = "/v5/user/create-api-key"
        params = {"api_key_name": api_key_name, "readOnly": read_only}
        if ips:
            params["ips"] = ips
        if permissions:
            params["permissions"] = permissions
        print(Fore.CYAN + f"# Creating API key {api_key_name}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    def frozen_sub_member(self, member_id: str, frozen: int) -> dict:
        """Freeze or unfreeze a sub-member.

        Endpoint: POST /v5/user/frozen-sub-member
        """
        endpoint = "/v5/user/frozen-sub-member"
        params = {"memberId": member_id, "frozen": frozen}
        print(
            Fore.CYAN
            + f"# {'Freezing' if frozen else 'Unfreezing'} sub-member {member_id}..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def update_api_key(
        self,
        api_key: str,
        api_key_name: str | None = None,
        read_only: int | None = None,
        ips: str | None = None,
        permissions: list[str] | None = None,
    ) -> dict:
        """Update an existing API key.

        Endpoint: POST /v5/user/update-api-key
        """
        endpoint = "/v5/user/update-api-key"
        params = {"api_key": api_key}
        if api_key_name:
            params["api_key_name"] = api_key_name
        if read_only is not None:
            params["readOnly"] = read_only
        if ips:
            params["ips"] = ips
        if permissions:
            params["permissions"] = permissions
        print(Fore.CYAN + f"# Updating API key {api_key}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    def delete_api_key(self, api_key: str) -> dict:
        """Delete an API key.

        Endpoint: POST /v5/user/delete-api-key
        """
        endpoint = "/v5/user/delete-api-key"
        params = {"api_key": api_key}
        print(Fore.CYAN + f"# Deleting API key {api_key}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    def set_trading_permission(
        self,
        member_id: str,
        unified_margin_trade: int | None = None,
        inverse_futures_trade: int | None = None,
    ) -> dict:
        """Set trading permission for a sub-member.

        Endpoint: POST /v5/user/set-trading-permission
        """
        endpoint = "/v5/user/set-trading-permission"
        params = {"memberId": member_id}
        if unified_margin_trade is not None:
            params["unifiedMarginTrade"] = unified_margin_trade
        if inverse_futures_trade is not None:
            params["inverseFuturesTrade"] = inverse_futures_trade
        print(
            Fore.CYAN
            + f"# Setting trading permission for sub-member {member_id}..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    # --- Spot Leveraged Token Endpoints ---

    def get_spot_leveraged_token_info(self, lt_coin: str | None = None) -> dict:
        """Retrieve Spot Leveraged Token information.

        Endpoint: GET /v5/spot-lever-token/info
        """
        endpoint = "/v5/spot-lever-token/info"
        params = {}
        if lt_coin:
            params["ltCoin"] = lt_coin
        print(Fore.CYAN + "# Retrieving Spot Leveraged Token info..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_spot_leveraged_token_order_record(
        self, lt_coin: str | None = None, order_id: str | None = None, limit: int = 50,
    ) -> dict:
        """Retrieve Spot Leveraged Token order records.

        Endpoint: GET /v5/spot-lever-token/order-record
        """
        endpoint = "/v5/spot-lever-token/order-record"
        params = {"limit": limit}
        if lt_coin:
            params["ltCoin"] = lt_coin
        if order_id:
            params["orderId"] = order_id
        print(
            Fore.CYAN
            + "# Retrieving Spot Leveraged Token order records..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def purchase_spot_leveraged_token(
        self, lt_coin: str, amount: float, serial_no: str | None = None,
    ) -> dict:
        """Purchase Spot Leveraged Token.

        Endpoint: POST /v5/spot-lever-token/purchase
        """
        endpoint = "/v5/spot-lever-token/purchase"
        params = {"ltCoin": lt_coin, "amount": str(amount)}
        if serial_no:
            params["serialNo"] = serial_no
        print(Fore.CYAN + f"# Purchasing {amount} of {lt_coin}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    def redeem_spot_leveraged_token(
        self, lt_coin: str, amount: float, serial_no: str | None = None,
    ) -> dict:
        """Redeem Spot Leveraged Token.

        Endpoint: POST /v5/spot-lever-token/redeem
        """
        endpoint = "/v5/spot-lever-token/redeem"
        params = {"ltCoin": lt_coin, "amount": str(amount)}
        if serial_no:
            params["serialNo"] = serial_no
        print(Fore.CYAN + f"# Redeeming {amount} of {lt_coin}..." + Style.RESET_ALL)
        return self._send_request("POST", endpoint, params)

    # --- Spot Margin Trade Endpoints ---

    def get_spot_margin_trade_data(self, spot_margin_mode: str | None = None) -> dict:
        """Retrieve Spot Margin Trade data.

        Endpoint: GET /v5/spot-margin-trade/data
        """
        endpoint = "/v5/spot-margin-trade/data"
        params = {}
        if spot_margin_mode:
            params["spotMarginMode"] = spot_margin_mode
        print(Fore.CYAN + "# Retrieving Spot Margin Trade data..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def set_spot_margin_leverage(self, symbol: str, leverage: float) -> dict:
        """Set leverage for Spot Margin Trade.

        Endpoint: POST /v5/spot-margin-trade/set-leverage
        """
        endpoint = "/v5/spot-margin-trade/set-leverage"
        params = {"symbol": symbol, "leverage": str(leverage)}
        print(
            Fore.CYAN
            + f"# Setting Spot Margin leverage for {symbol} to {leverage}x..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def toggle_spot_margin_trade_mode(self, spot_margin_mode: str) -> dict:
        """Toggle Spot Margin Trade mode.

        Endpoint: POST /v5/spot-margin-trade/toggle-trade-mode
        """
        endpoint = "/v5/spot-margin-trade/toggle-trade-mode"
        params = {"spotMarginMode": spot_margin_mode}
        print(
            Fore.CYAN
            + f"# Toggling Spot Margin Trade mode to {spot_margin_mode}..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def borrow_spot_margin(self, coin: str, amount: float) -> dict:
        """Borrow for Spot Margin Trade.

        Endpoint: POST /v5/spot-margin-trade/borrow
        """
        endpoint = "/v5/spot-margin-trade/borrow"
        params = {"coin": coin, "amount": str(amount)}
        print(
            Fore.CYAN
            + f"# Borrowing {amount} {coin} for Spot Margin Trade..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def repay_spot_margin(self, coin: str, amount: float) -> dict:
        """Repay Spot Margin Trade.

        Endpoint: POST /v5/spot-margin-trade/repay
        """
        endpoint = "/v5/spot-margin-trade/repay"
        params = {"coin": coin, "amount": str(amount)}
        print(
            Fore.CYAN
            + f"# Repaying {amount} {coin} for Spot Margin Trade..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def get_spot_margin_loan_info(self, coin: str | None = None) -> dict:
        """Retrieve Spot Margin Loan information.

        Endpoint: GET /v5/spot-margin-trade/loan-info
        """
        endpoint = "/v5/spot-margin-trade/loan-info"
        params = {}
        if coin:
            params["coin"] = coin
        print(Fore.CYAN + "# Retrieving Spot Margin Loan info..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_spot_margin_repay_history(
        self, coin: str | None = None, limit: int = 50,
    ) -> dict:
        """Retrieve Spot Margin Repay history.

        Endpoint: GET /v5/spot-margin-trade/repay-history
        """
        endpoint = "/v5/spot-margin-trade/repay-history"
        params = {"limit": limit}
        if coin:
            params["coin"] = coin
        print(Fore.CYAN + "# Retrieving Spot Margin Repay history..." + Style.RESET_ALL)
        return self._send_request("GET", endpoint, params)

    def get_spot_margin_borrow_history(
        self, coin: str | None = None, limit: int = 50,
    ) -> dict:
        """Retrieve Spot Margin Borrow history.

        Endpoint: GET /v5/spot-margin-trade/borrow-history
        """
        endpoint = "/v5/spot-margin-trade/borrow-history"
        params = {"limit": limit}
        if coin:
            params["coin"] = coin
        print(
            Fore.CYAN + "# Retrieving Spot Margin Borrow history..." + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_spot_margin_interest_history(
        self, coin: str | None = None, limit: int = 50,
    ) -> dict:
        """Retrieve Spot Margin Interest history.

        Endpoint: GET /v5/spot-margin-trade/interest-history
        """
        endpoint = "/v5/spot-margin-trade/interest-history"
        params = {"limit": limit}
        if coin:
            params["coin"] = coin
        print(
            Fore.CYAN + "# Retrieving Spot Margin Interest history..." + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    # --- Copy Trading Endpoints ---

    def get_copy_trading_order_list(
        self, category: str, symbol: str | None = None, limit: int = 50,
    ) -> dict:
        """Retrieve copy trading order list.

        Endpoint: GET /v5/copytrading/order/list
        """
        endpoint = "/v5/copytrading/order/list"
        params = {"category": category, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        print(
            Fore.CYAN
            + f"# Retrieving copy trading order list for {category}..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_copy_trading_order_history(
        self, category: str, symbol: str | None = None, limit: int = 50,
    ) -> dict:
        """Retrieve copy trading order history.

        Endpoint: GET /v5/copytrading/order/history
        """
        endpoint = "/v5/copytrading/order/history"
        params = {"category": category, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        print(
            Fore.CYAN
            + f"# Retrieving copy trading order history for {category}..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_copy_trading_position_list(
        self, category: str, symbol: str | None = None,
    ) -> dict:
        """Retrieve copy trading position list.

        Endpoint: GET /v5/copytrading/position/list
        """
        endpoint = "/v5/copytrading/position/list"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        print(
            Fore.CYAN
            + f"# Retrieving copy trading position list for {category}..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def get_copy_trading_closed_pnl(
        self, category: str, symbol: str | None = None, limit: int = 50,
    ) -> dict:
        """Retrieve copy trading closed PNL.

        Endpoint: GET /v5/copytrading/position/closed-pnl
        """
        endpoint = "/v5/copytrading/position/closed-pnl"
        params = {"category": category, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        print(
            Fore.CYAN
            + f"# Retrieving copy trading closed PNL for {category}..."
            + Style.RESET_ALL,
        )
        return self._send_request("GET", endpoint, params)

    def close_copy_trading_position(
        self,
        category: str,
        symbol: str,
        order_type: str = "Market",
        price: float | None = None,
    ) -> dict:
        """Close a copy trading position.

        Endpoint: POST /v5/copytrading/order/close-position
        """
        endpoint = "/v5/copytrading/order/close-position"
        params = {"category": category, "symbol": symbol, "orderType": order_type}
        if price:
            params["price"] = str(price)
        print(
            Fore.CYAN
            + f"# Closing copy trading position for {symbol}..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    def cancel_copy_trading_order(
        self,
        category: str,
        symbol: str,
        order_id: str | None = None,
        order_link_id: str | None = None,
    ) -> dict:
        """Cancel a copy trading order.

        Endpoint: POST /v5/copytrading/order/cancel
        """
        endpoint = "/v5/copytrading/order/cancel"
        params = {"category": category, "symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        if order_link_id:
            params["orderLinkId"] = order_link_id
        print(
            Fore.CYAN
            + f"# Cancelling copy trading order for {symbol}..."
            + Style.RESET_ALL,
        )
        return self._send_request("POST", endpoint, params)

    # --- Risk Management and Profit Checks ---

    def calculate_position_size(
        self,
        symbol: str,
        risk_percentage: float,
        stop_loss_distance: float,
        account_type: str = "UNIFIED",
        leverage: float = 1.0,
    ) -> float:
        """Calculate position size based on risk percentage and account balance with enhanced validation.

        Args:
            symbol (str): Trading pair.
            risk_percentage (float): Percentage of account to risk (e.g., 1 for 1%).
            stop_loss_distance (float): Distance to stop-loss in price units.
            account_type (str): Account type (UNIFIED, SPOT, etc.).
            leverage (float): Leverage to apply.

        Returns:
            float: Position size in base currency.

        """
        if risk_percentage <= 0 or risk_percentage > 100:
            logger.error(f"Invalid risk percentage: {risk_percentage}")
            print(
                Fore.RED
                + "# Risk percentage must be between 0 and 100!"
                + Style.RESET_ALL,
            )
            return 0.0

        if stop_loss_distance <= 0:
            logger.error("Stop-loss distance must be positive")
            print(
                Fore.RED
                + "# Stop-loss distance cannot be zero or negative for position sizing!"
                + Style.RESET_ALL,
            )
            return 0.0

        if leverage <= 0:
            logger.error(f"Invalid leverage: {leverage}")
            print(Fore.RED + "# Leverage must be positive!" + Style.RESET_ALL)
            return 0.0

        balance = self.get_wallet_balance(account_type)
        if not balance.get("list"):
            logger.warning("No balance found for position sizing")
            print(Fore.RED + "# No balance found!" + Style.RESET_ALL)
            return 0.0

        try:
            total_equity = float(balance["list"][0]["totalEquity"])
            risk_amount = total_equity * (risk_percentage / 100)
            position_size = (risk_amount * leverage) / stop_loss_distance

            logger.info(
                f"Position size calculated for {symbol}: {position_size} units (Risk: {risk_percentage}%, SL Distance: {stop_loss_distance})",
            )
            print(
                Fore.CYAN
                + f"# Calculated position size for {symbol}: {position_size} units"
                + Style.RESET_ALL,
            )

            return position_size

        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error calculating position size: {e!s}")
            print(
                Fore.RED + f"# Error calculating position size: {e!s}" + Style.RESET_ALL,
            )
            return 0.0

    def monitor_profit(
        self,
        symbol: str,
        profit_target: float,
        action: str = "partial_close",
        close_percentage: float = 50,
    ):
        """Monitor profit and trigger actions when target is reached.

        Args:
            symbol (str): Trading pair.
            profit_target (float): Target profit percentage (e.g., 5 for 5%).
            action (str): Action to take ("partial_close", "set_take_profit", "close").
            close_percentage (float): Percentage to close for partial_close action.

        """
        if symbol in self.positions:
            self.positions[symbol]["profit_target"] = profit_target
            self.positions[symbol]["profit_action"] = action
            self.positions[symbol]["close_percentage"] = close_percentage
            print(
                Fore.CYAN
                + f"# Monitoring {symbol} for {profit_target}% profit with action {action}..."
                + Style.RESET_ALL,
            )
        else:
            print(
                Fore.RED
                + f"# No position found for {symbol} to monitor profit!"
                + Style.RESET_ALL,
            )

    # --- Break-Even and Trailing Stop-Loss Logic ---

    def enable_break_even(self, symbol: str, enable: bool = True):
        """Enable or disable break-even enchantment for a position."""
        if symbol in self.positions:
            self.positions[symbol]["break_even_enabled"] = enable
            print(
                Fore.CYAN
                + f"# Break-even {'enabled' if enable else 'disabled'} for {symbol}..."
                + Style.RESET_ALL,
            )
        else:
            print(Fore.RED + f"# No position found for {symbol}!" + Style.RESET_ALL)

    def enable_trailing_stop(
        self, symbol: str, enable: bool = True, distance: float | None = None,
    ):
        """Enable or disable trailing stop-loss enchantment for a position."""
        if symbol in self.positions:
            self.positions[symbol]["tsl_enabled"] = enable
            if distance:
                self.positions[symbol]["tsl_distance"] = distance
            print(
                Fore.CYAN
                + f"# Trailing stop {'enabled' if enable else 'disabled'} for {symbol}..."
                + Style.RESET_ALL,
            )
        else:
            print(Fore.RED + f"# No position found for {symbol}!" + Style.RESET_ALL)

    # --- WebSocket Functions ---

    def connect_private_ws(self):
        """Forge a connection to the private WebSocket stream with enhanced reconnection logic."""
        if self.ws_private and self.ws_private.sock and self.ws_private.sock.connected:
            logger.info("Private WebSocket already connected")
            return

        try:
            self.ws_private = websocket.WebSocketApp(
                self.ws_private_url,
                on_message=self._on_message_private,
                on_error=self._on_error,
                on_close=self._on_close_private,
                on_open=self._on_open_private,
            )
            self.ws_private_thread = threading.Thread(target=self._run_private_ws)
            self.ws_private_thread.daemon = True
            self.ws_private_thread.start()

            logger.info("Private WebSocket connection initiated")
            print(Fore.CYAN + "# Opening private WebSocket portal..." + Style.RESET_ALL)

        except Exception as e:
            logger.error(f"Failed to connect private WebSocket: {e!s}")
            self.metrics.record_error("ws_private_connect_failed")

    def _run_private_ws(self):
        """Run private WebSocket with reconnection logic."""
        while not self.shutdown_event.is_set():
            try:
                self.ws_private.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                logger.error(f"Private WebSocket error: {e!s}")
                self.metrics.record_error("ws_private_error")

            if not self.shutdown_event.is_set():
                self._handle_ws_reconnection("private")

    def connect_public_ws(self):
        """Forge a connection to the public WebSocket stream with enhanced reconnection logic."""
        if self.ws_public and self.ws_public.sock and self.ws_public.sock.connected:
            logger.info("Public WebSocket already connected")
            return

        try:
            self.ws_public = websocket.WebSocketApp(
                self.ws_public_url,
                on_message=self._on_message_public,
                on_error=self._on_error,
                on_close=self._on_close_public,
                on_open=self._on_open_public,
            )
            self.ws_public_thread = threading.Thread(target=self._run_public_ws)
            self.ws_public_thread.daemon = True
            self.ws_public_thread.start()

            logger.info("Public WebSocket connection initiated")
            print(Fore.CYAN + "# Opening public WebSocket portal..." + Style.RESET_ALL)

        except Exception as e:
            logger.error(f"Failed to connect public WebSocket: {e!s}")
            self.metrics.record_error("ws_public_connect_failed")

    def _run_public_ws(self):
        """Run public WebSocket with reconnection logic."""
        while not self.shutdown_event.is_set():
            try:
                self.ws_public.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                logger.error(f"Public WebSocket error: {e!s}")
                self.metrics.record_error("ws_public_error")

            if not self.shutdown_event.is_set():
                self._handle_ws_reconnection("public")

    def _handle_ws_reconnection(self, ws_type: str):
        """Handle WebSocket reconnection with exponential backoff."""
        if self.ws_reconnect_attempts >= self.max_reconnect_attempts:
            logger.error(f"Max reconnection attempts reached for {ws_type} WebSocket")
            return

        self.ws_reconnect_attempts += 1
        delay = min(2**self.ws_reconnect_attempts, 60)  # Max 60 seconds

        logger.info(
            f"Reconnecting {ws_type} WebSocket in {delay} seconds (attempt {self.ws_reconnect_attempts})",
        )
        time.sleep(delay)

        if ws_type == "private":
            self.connect_private_ws()
        else:
            self.connect_public_ws()

    def close_ws(self):
        """Sever all WebSocket connections gracefully."""
        logger.info("Closing WebSocket connections...")

        if self.ws_private:
            self.ws_private.close()
        if self.ws_public:
            self.ws_public.close()

        # Wait for threads to finish
        if self.ws_private_thread and self.ws_private_thread.is_alive():
            self.ws_private_thread.join(timeout=5)
        if self.ws_public_thread and self.ws_public_thread.is_alive():
            self.ws_public_thread.join(timeout=5)

        self.connection_health["ws_private"] = False
        self.connection_health["ws_public"] = False

        print(Fore.RED + "# All WebSocket portals have been sealed." + Style.RESET_ALL)

    def _on_message_private(self, ws, message):
        """Handle incoming private WebSocket messages with enhanced processing."""
        try:
            data = json.loads(message)
            topic = data.get("topic")

            if data.get("op") == "pong":
                self.last_heartbeat["private"] = time.time()
                return

            self.metrics.increment("ws_private_messages")
            logger.debug(f"Private WS message: {topic}")

            if topic == "position":
                print(Fore.BLUE + "# Position update received!" + Style.RESET_ALL)
                self._handle_position_update(data)
            elif topic == "order":
                print(Fore.BLUE + "# Order update received!" + Style.RESET_ALL)
                self._handle_order_update(data)
            elif topic == "wallet":
                print(Fore.BLUE + "# Wallet update received!" + Style.RESET_ALL)
                self._handle_wallet_update(data)
            else:
                logger.debug(f"Unhandled private message topic: {topic}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse private WebSocket message: {e!s}")
            self.metrics.record_error("ws_private_parse_error")
        except Exception as e:
            logger.error(f"Error handling private WebSocket message: {e!s}")
            self.metrics.record_error("ws_private_handler_error")

    def _on_message_public(self, ws, message):
        """Handle incoming public WebSocket messages with enhanced processing."""
        try:
            data = json.loads(message)
            topic = data.get("topic", "")

            if data.get("op") == "pong":
                self.last_heartbeat["public"] = time.time()
                return

            self.metrics.increment("ws_public_messages")
            logger.debug(f"Public WS message: {topic}")

            if "ticker" in topic:
                self._handle_ticker_update(data)
            elif "orderbook" in topic:
                self._handle_orderbook_update(data)
            elif "kline" in topic:
                self._handle_kline_update(data)
            else:
                logger.debug(f"Unhandled public message topic: {topic}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse public WebSocket message: {e!s}")
            self.metrics.record_error("ws_public_parse_error")
        except Exception as e:
            logger.error(f"Error handling public WebSocket message: {e!s}")
            self.metrics.record_error("ws_public_handler_error")

    def _on_error(self, ws, error):
        """Handle WebSocket errors with enhanced logging."""
        logger.error(f"WebSocket error: {error!s}")
        self.metrics.record_error("ws_error")

    def _on_close_private(self, ws, close_status_code, close_msg):
        """Handle private WebSocket close with enhanced logging."""
        logger.warning(f"Private WebSocket closed: {close_status_code} - {close_msg}")
        self.connection_health["ws_private"] = False
        self.metrics.record_error("ws_private_closed")

    def _on_close_public(self, ws, close_status_code, close_msg):
        """Handle public WebSocket close with enhanced logging."""
        logger.warning(f"Public WebSocket closed: {close_status_code} - {close_msg}")
        self.connection_health["ws_public"] = False
        self.metrics.record_error("ws_public_closed")

    def _on_open_private(self, ws):
        """Handle private WebSocket open with authentication."""
        logger.info("Private WebSocket connected")
        self.connection_health["ws_private"] = True
        self.ws_reconnect_attempts = 0  # Reset on successful connection

        # Authenticate private WebSocket
        timestamp = int(time.time() * 1000)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            f"GET/realtime{timestamp}".encode(),
            hashlib.sha256,
        ).hexdigest()

        auth_message = {"op": "auth", "args": [self.api_key, timestamp, signature]}

        ws.send(json.dumps(auth_message))
        print(
            Fore.GREEN
            + "# Private WebSocket portal opened and authenticated!"
            + Style.RESET_ALL,
        )
        # Subscribe to essential private topics upon connection
        self.subscribe_private_ws(["position", "order", "wallet"])

    def _on_open_public(self, ws):
        """Handle public WebSocket open."""
        logger.info("Public WebSocket connected")
        self.connection_health["ws_public"] = True
        self.ws_reconnect_attempts = 0  # Reset on successful connection
        print(Fore.GREEN + "# Public WebSocket portal opened!" + Style.RESET_ALL)
        # Subscribe to essential public topics upon connection
        self.subscribe_public_ws(["tickers.BTCUSDT", "kline.1.BTCUSDT"])

    def _handle_position_update(self, data):
        """Handle position updates with enhanced tracking."""
        try:
            positions_data = data.get("data", [])
            for pos_data in positions_data:
                symbol = pos_data.get("symbol")
                if symbol and symbol in self.positions:
                    position = self.positions[symbol]
                    position.entry_price = float(pos_data.get("avgPrice", 0))
                    position.unrealized_pnl = float(pos_data.get("unrealisedPnl", 0))
                    position.size = float(pos_data.get("size", 0))
                    position.last_update = datetime.now()

                    logger.info(
                        f"Position updated for {symbol}: PnL={position.unrealized_pnl}",
                    )

                    # Check for profit targets and other conditions
                    self._check_position_conditions(symbol, position)

        except Exception as e:
            logger.error(f"Error handling position update: {e!s}")

    def _handle_order_update(self, data):
        """Handle order updates with enhanced logging."""
        try:
            orders_data = data.get("data", [])
            for order_data in orders_data:
                symbol = order_data.get("symbol")
                order_status = order_data.get("orderStatus")
                order_id = order_data.get("orderId")

                logger.info(f"Order update: {symbol} - {order_id} - {order_status}")
                self.metrics.increment(f"order_status_{order_status.lower()}")

        except Exception as e:
            logger.error(f"Error handling order update: {e!s}")

    def _handle_wallet_update(self, data):
        """Handle wallet updates with enhanced logging."""
        try:
            wallet_data = data.get("data", [])
            for wallet in wallet_data:
                account_type = wallet.get("accountType")
                logger.info(f"Wallet update for {account_type} account")

        except Exception as e:
            logger.error(f"Error handling wallet update: {e!s}")

    def _handle_ticker_update(self, data):
        """Handle ticker updates."""
        try:
            ticker_data = data.get("data")
            if ticker_data:
                symbol = ticker_data.get("symbol")
                price = ticker_data.get("lastPrice")
                logger.debug(f"Ticker update: {symbol} @ {price}")

        except Exception as e:
            logger.error(f"Error handling ticker update: {e!s}")

    def _handle_orderbook_update(self, data):
        """Handle orderbook updates."""
        try:
            # Process orderbook data
            logger.debug("Orderbook update received")

        except Exception as e:
            logger.error(f"Error handling orderbook update: {e!s}")

    def _handle_kline_update(self, data):
        """Handle kline updates."""
        try:
            # Process kline data
            logger.debug("Kline update received")

        except Exception as e:
            logger.error(f"Error handling kline update: {e!s}")

    def _check_position_conditions(self, symbol: str, position: Position):
        """Check position conditions for automated actions."""
        try:
            if not position.entry_price or not position.unrealized_pnl:
                return

            # Calculate profit percentage
            profit_pct = (
                position.unrealized_pnl / abs(position.entry_price * position.size)
            ) * 100

            # Check profit target
            if position.profit_target and profit_pct >= position.profit_target:
                logger.info(f"Profit target reached for {symbol}: {profit_pct:.2f}%")
                self._execute_profit_action(symbol, position)

            # Check break-even conditions
            if position.break_even_enabled and profit_pct > 0:
                logger.info(f"Moving stop-loss to break-even for {symbol}")
                # Implement break-even logic here

            # Check trailing stop conditions
            if position.tsl_enabled and position.tsl_distance:
                logger.info(f"Updating trailing stop for {symbol}")
                # Implement trailing stop logic here

        except Exception as e:
            logger.error(f"Error checking position conditions for {symbol}: {e!s}")

    def _execute_profit_action(self, symbol: str, position: Position):
        """Execute profit-taking action."""
        try:
            if position.profit_action == "partial_close":
                # Close partial position
                close_qty = position.size * (position.close_percentage / 100)
                logger.info(f"Executing partial close for {symbol}: {close_qty} units")
                # Implement partial close logic here
            elif position.profit_action == "close":
                # Close entire position
                logger.info(f"Executing full close for {symbol}")
                # Implement full close logic here

        except Exception as e:
            logger.error(f"Error executing profit action for {symbol}: {e!s}")

    def get_system_status(self) -> dict:
        """Get comprehensive system status and health information."""
        status = {
            "timestamp": datetime.now().isoformat(),
            "connection_health": self.connection_health.copy(),
            "metrics": self.metrics.get_stats(),
            "positions_tracked": len(self.positions),
            "circuit_breaker_state": self.circuit_breaker.state,
            "rate_limiter_tokens": self.rate_limiter.tokens,
            "last_heartbeat": self.last_heartbeat.copy(),
        }

        # Check WebSocket health based on heartbeat
        now = time.time()
        for ws_type, last_beat in self.last_heartbeat.items():
            if now - last_beat > 60:  # No heartbeat for 60 seconds
                status["connection_health"][f"ws_{ws_type}"] = False

        return status

    def check_health(self) -> bool:
        """Perform a comprehensive health check on API and WebSocket connectivity."""
        print(
            Fore.CYAN
            + "# Performing an enhanced ethereal health check..."
            + Style.RESET_ALL,
        )

        health_status = self.get_system_status()

        # API Health Check
        try:
            api_status = self._send_request("GET", "/v5/market/time", {}, retries=1)
            api_ok = bool(api_status)
            self.connection_health["api"] = api_ok
        except Exception as e:
            logger.error(f"API health check failed: {e!s}")
            api_ok = False
            self.connection_health["api"] = False

        # Overall health assessment
        all_healthy = (
            self.connection_health["api"]
            and self.connection_health["ws_private"]
            and self.connection_health["ws_public"]
        )

        print(
            Fore.GREEN
            + f"# Enhanced Health Report:\n{json.dumps(health_status, indent=2)}"
            + Style.RESET_ALL,
        )

        if all_healthy:
            print(Fore.GREEN + "# All systems operational!" + Style.RESET_ALL)
        else:
            print(Fore.YELLOW + "# Some systems require attention!" + Style.RESET_ALL)

        return all_healthy

    # --- existing code ---


### Enhanced Example Usage
if __name__ == "__main__":
    print(
        Fore.MAGENTA
        + "### Enhanced mystical ritual to test the Bybit V5 Wizard ###"
        + Style.RESET_ALL,
    )

    config_path = os.path.expanduser("~/.bybit_config")
    if not os.path.exists(config_path):
        print(
            Fore.RED
            + "Error: ~/.bybit_config not found. Please create it with your API credentials."
            + Style.RESET_ALL,
        )
        print(
            Fore.YELLOW
            + 'Example: echo \'{"api_key": "YOUR_API_KEY", "api_secret": "YOUR_API_SECRET", "testnet": true}\' > ~/.bybit_config'
            + Style.RESET_ALL,
        )
        exit()

    try:
        bybit_wizard = BybitV5Wizard()

        # Connect to WebSockets
        bybit_wizard.connect_private_ws()
        bybit_wizard.connect_public_ws()

        # Give time for connections to establish
        time.sleep(5)

        # Comprehensive health check
        bybit_wizard.check_health()

        # Display system status
        status = bybit_wizard.get_system_status()
        print(
            Fore.CYAN
            + f"\n# System Status:\n{json.dumps(status, indent=2)}"
            + Style.RESET_ALL,
        )

        # --- existing demo code ---

        print(Fore.CYAN + "\n--- Enhanced Market Data Spells ---" + Style.RESET_ALL)
        server_time = bybit_wizard.get_server_time()
        print(f"Server Time: {server_time}")

        tickers = bybit_wizard.get_tickers(category="linear", symbol="BTCUSDT")
        print(f"BTCUSDT Ticker: {tickers}")

        kline_data = bybit_wizard.get_kline(
            category="linear", symbol="BTCUSDT", interval="1",
        )
        print(
            f"BTCUSDT 1-min Kline (first entry): {kline_data.get('list', [])[0] if kline_data.get('list') else 'N/A'}",
        )

        print(
            Fore.CYAN + "\n--- Enhanced Account Management Spells ---" + Style.RESET_ALL,
        )
        account_balance = bybit_wizard.get_wallet_balance(
            account_type="UNIFIED", coin="USDT",
        )
        print(f"USDT Balance: {account_balance}")

        account_info = bybit_wizard.get_account_info()
        print(f"Account Info: {account_info}")

        fee_rate = bybit_wizard.get_fee_rate(category="linear", symbol="BTCUSDT")
        print(f"BTCUSDT Fee Rate: {fee_rate}")

        print(
            Fore.CYAN + "\n--- Enhanced Position & Trade Spells ---" + Style.RESET_ALL,
        )
        symbol_to_trade = "BTCUSDT"

        # Enhanced position sizing calculation
        calculated_qty = bybit_wizard.calculate_position_size(
            symbol=symbol_to_trade,
            risk_percentage=1,
            stop_loss_distance=500,
            leverage=10,
        )
        print(f"Calculated Position Quantity: {calculated_qty}")

        # Place enhanced market order
        order_result = bybit_wizard.place_market_order(
            symbol=symbol_to_trade,
            side="Buy",
            qty=0.001,
            break_even=True,
            tsl=True,
            tsl_distance=200,
            profit_target=0.5,
        )
        print(f"Enhanced Market Order Result: {order_result}")

        # Monitor for updates
        print(
            Fore.CYAN
            + "\n# Enhanced wizard is now watching the market with mystical algorithms. Press Ctrl+C to stop."
            + Style.RESET_ALL,
        )

        # Enhanced monitoring loop
        while True:
            try:
                # Periodic health checks
                if int(time.time()) % 300 == 0:  # Every 5 minutes
                    bybit_wizard.check_health()

                # Display metrics periodically
                if int(time.time()) % 60 == 0:  # Every minute
                    metrics = bybit_wizard.metrics.get_stats()
                    logger.info(f"Current metrics: {metrics}")

                time.sleep(30)

            except KeyboardInterrupt:
                break

    except KeyboardInterrupt:
        print(
            Fore.RED
            + "\n# The enhanced wizard's journey ends. Script terminated by user."
            + Style.RESET_ALL,
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e!s}")
        logger.error(traceback.format_exc())
        print(
            Fore.RED
            + f"\n# An unexpected error befell the enhanced wizard: {e!s}"
            + Style.RESET_ALL,
        )
    finally:
        if "bybit_wizard" in locals():
            bybit_wizard.close_ws()
            final_status = bybit_wizard.get_system_status()
            print(
                Fore.CYAN
                + f"\n# Final System Status:\n{json.dumps(final_status, indent=2)}"
                + Style.RESET_ALL,
            )
