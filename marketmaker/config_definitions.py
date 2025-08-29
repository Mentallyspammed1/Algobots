import os
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timezone
import logging
from collections import deque
import time
import numpy as np # Added for np.sign

@dataclass
class TradeMetrics:
    total_trades: int = 0
    gross_profit: Decimal = Decimal("0")
    gross_loss: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    realized_pnl: Decimal = Decimal("0")
    current_asset_holdings: Decimal = Decimal("0") # Net position (positive for long, negative for short)
    average_entry_price: Decimal = Decimal("0") # Average entry price for the net position
    last_pnl_update_timestamp: datetime | None = None

    @property
    def net_realized_pnl(self) -> Decimal:
        return self.realized_pnl - self.total_fees

    def update_win_rate(self):
        self.win_rate = (
            (self.wins / self.total_trades * 100.0) if self.total_trades > 0 else 0.0
        )

    def update_position_and_pnl(self, side: str, quantity: Decimal, price: Decimal):
        # This method handles both buy and sell fills, updating net position and PnL
        # quantity is always positive
        # price is the fill price

        # Calculate PnL for closing part of a position
        realized_pnl_on_fill = Decimal("0")
        if self.current_asset_holdings != Decimal("0") and np.sign(self.current_asset_holdings) != np.sign(quantity if side == "Buy" else -quantity):
            # Closing or flipping a position
            qty_closed = min(abs(self.current_asset_holdings), quantity)
            if self.current_asset_holdings > 0 and side == "Sell": # Closing long
                realized_pnl_on_fill = (price - self.average_entry_price) * qty_closed
            elif self.current_asset_holdings < 0 and side == "Buy": # Closing short
                realized_pnl_on_fill = (self.average_entry_price - price) * qty_closed
            self.realized_pnl += realized_pnl_on_fill

            if realized_pnl_on_fill > 0:
                self.gross_profit += realized_pnl_on_fill
                self.wins += 1
            elif realized_pnl_on_fill < 0:
                self.gross_loss += abs(realized_pnl_on_fill)
                self.losses += 1

        # Update net position and average entry price
        if side == "Buy":
            new_holdings = self.current_asset_holdings + quantity
            if new_holdings != Decimal("0"):
                if np.sign(new_holdings) == np.sign(self.current_asset_holdings) or self.current_asset_holdings == Decimal("0"):
                    # Adding to same-direction position or opening new long
                    self.average_entry_price = ((self.average_entry_price * abs(self.current_asset_holdings)) + (price * quantity)) / abs(new_holdings)
                else: # Flipping from short to long, or reducing short
                    # Average entry price remains the same for the remaining position
                    pass
            else: # Position becomes zero
                self.average_entry_price = Decimal("0")
            self.current_asset_holdings = new_holdings
        elif side == "Sell":
            new_holdings = self.current_asset_holdings - quantity
            if new_holdings != Decimal("0"):
                if np.sign(new_holdings) == np.sign(self.current_asset_holdings) or self.current_asset_holdings == Decimal("0"):
                    # Adding to same-direction position or opening new short
                    self.average_entry_price = ((self.average_entry_price * abs(self.current_asset_holdings)) + (price * quantity)) / abs(new_holdings)
                else: # Flipping from long to short, or reducing long
                    # Average entry price remains the same for the remaining position
                    pass
            else: # Position becomes zero
                self.average_entry_price = Decimal("0")
            self.current_asset_holdings = new_holdings
        
        self.last_pnl_update_timestamp = datetime.now(timezone.utc)
        self.total_trades += 1 # Count each fill as a trade for win rate purposes
        self.update_win_rate()

    def calculate_unrealized_pnl(self, current_price: Decimal) -> Decimal:
        if self.current_asset_holdings != Decimal("0") and self.average_entry_price != Decimal("0"):
            return (current_price - self.average_entry_price) * self.current_asset_holdings
        return Decimal("0")


@dataclass(frozen=True)
class InventoryStrategyConfig:
    enabled: bool = True
    skew_intensity: Decimal = Decimal("0.5")
    max_inventory_ratio: Decimal = Decimal("0.5")


@dataclass(frozen=True)
class DynamicSpreadConfig:
    enabled: bool = True
    volatility_window_sec: int = 60
    volatility_multiplier: Decimal = Decimal("2.0")
    min_spread_pct: Decimal = Decimal("0.0005")
    max_spread_pct: Decimal = Decimal("0.01")
    price_change_smoothing_factor: Decimal = Decimal("0.2")
    default_volatility: Decimal = Decimal("0.001")


@dataclass(frozen=True)
class CircuitBreakerConfig:
    enabled: bool = True
    pause_threshold_pct: Decimal = Decimal("0.02")
    check_window_sec: int = 10
    pause_duration_sec: int = 60
    cool_down_after_trip_sec: int = 300
    max_daily_loss_pct: Decimal = Decimal("0.05")


@dataclass(frozen=True)
class StrategyConfig:
    base_spread_pct: Decimal = Decimal("0.001")
    base_order_size_pct_of_balance: Decimal = Decimal("0.005")
    order_stale_threshold_pct: Decimal = Decimal("0.0005")
    min_profit_spread_after_fees_pct: Decimal = Decimal("0.0002")
    max_outstanding_orders: int = 2
    max_position_size: Decimal = Decimal("1000")
    inventory: InventoryStrategyConfig = field(default_factory=InventoryStrategyConfig)
    dynamic_spread: DynamicSpreadConfig = field(default_factory=DynamicSpreadConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)


@dataclass(frozen=True)
class SystemConfig:
    loop_interval_sec: float = 0.5
    order_refresh_interval_sec: float = 5.0
    ws_heartbeat_sec: int = 30
    cancellation_rate_limit_sec: float = 0.2
    status_report_interval_sec: int = 30
    ws_reconnect_attempts: int = 5
    ws_reconnect_initial_delay_sec: int = 5
    ws_reconnect_max_delay_sec: int = 60
    api_retry_attempts: int = 5
    api_retry_initial_delay_sec: float = 0.5
    api_retry_max_delay_sec: float = 10.0
    health_check_interval_sec: int = 10
    api_timeout_sec: int = 30


@dataclass(frozen=True)
class FilesConfig:
    log_level: str = "INFO"
    log_file: str = "market_maker.log"
    state_file: str = "market_maker_state.pkl"
    db_file: str = "market_maker.db"


@dataclass(frozen=True)
class Config:
    api_key: str = field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BYBIT_API_SECRET", ""))
    testnet: bool = os.getenv("BYBIT_TESTNET", "true").lower() == "true"
    trading_mode: str = "DRY_RUN"
    symbol: str = "XLMUSDT"
    category: str = "linear"
    leverage: Decimal = Decimal("1")
    min_order_value_usd: Decimal = Decimal("10")
    max_order_size_pct: Decimal = Decimal("0.1")
    max_net_exposure_usd: Decimal = Decimal("500")
    order_type: str = "Limit"
    time_in_force: str = "GTC"
    post_only: bool = True
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    system: SystemConfig = field(default_factory=SystemConfig)
    files: FilesConfig = field(default_factory=FilesConfig)
    initial_dry_run_capital: Decimal = Decimal("10000")
    dry_run_price_drift_mu: float = 0.0
    dry_run_price_volatility_sigma: float = 0.0001
    dry_run_time_step_dt: float = 1.0

    base_currency: str = field(init=False)
    quote_currency: str = field(init=False)

    def __post_init__(self):
        def _set_attr(name, value):
            object.__setattr__(self, name, value)

        if self.symbol.endswith("USDT"):
            _set_attr("base_currency", self.symbol[:-4])
            _set_attr("quote_currency", "USDT")
        elif self.symbol.endswith("USD"):
            _set_attr("base_currency", self.symbol[:-3])
            _set_attr("quote_currency", "USD")
        elif len(self.symbol) == 6:
            _set_attr("base_currency", self.symbol[:3])
            _set_attr("quote_currency", self.symbol[3:])
        else:
            raise ConfigurationError(
                f"Cannot parse base/quote currency from symbol: {self.symbol}. Use a standard format (e.g., BTCUSDT)."
            )

        if self.trading_mode == "TESTNET":
            _set_attr("testnet", True)
        elif self.trading_mode == "LIVE":
            _set_attr("testnet", False)

        if self.trading_mode not in ["DRY_RUN", "SIMULATION"] and (
            not self.api_key or not self.api_secret
        ):
            raise ConfigurationError(
                "API_KEY and API_SECRET must be set in .env for TESTNET or LIVE trading_mode."
            )

        if self.category in ["linear", "inverse"]:
            if self.leverage <= 0:
                raise ConfigurationError(
                    "Leverage must be a positive decimal for linear/inverse categories."
                )
        elif self.category == "spot":
            if self.leverage != Decimal("1"):
                _set_attr("leverage", Decimal("1"))
                logging.getLogger("MarketMakerBot").warning(
                    "Leverage is not applicable for spot trading. Setting leverage to 1."
                )

        if self.strategy.inventory.enabled and self.max_net_exposure_usd <= 0:
            raise ConfigurationError(
                "max_net_exposure_usd must be positive when inventory strategy is enabled."
            )
        if not (Decimal("0") < self.max_order_size_pct <= Decimal("1")):
            raise ConfigurationError(
                "max_order_size_pct must be between 0 and 1 (exclusive)."
            )
        if self.min_order_value_usd <= Decimal("0"):
            raise ConfigurationError("min_order_value_usd must be positive.")
        if self.max_net_exposure_usd < Decimal("0"):
            raise ConfigurationError("max_net_exposure_usd cannot be negative.")
        if self.strategy.base_spread_pct <= Decimal("0"):
            raise ConfigurationError("base_spread_pct must be positive.")
        if self.category not in ["linear", "inverse", "spot"]:
            raise ConfigurationError(f"Unsupported category: {self.category}")
        if self.strategy.max_outstanding_orders < 0:
            raise ConfigurationError("max_outstanding_orders cannot be negative.")

        if self.strategy.dynamic_spread.enabled:
            if not (
                Decimal("0")
                <= self.strategy.dynamic_spread.min_spread_pct
                <= self.strategy.dynamic_spread.max_spread_pct
            ):
                raise ConfigurationError(
                    "Dynamic spread min/max percentages are invalid."
                )
            if not (
                Decimal("0")
                < self.strategy.dynamic_spread.price_change_smoothing_factor
                < Decimal("1")
            ):
                raise ConfigurationError(
                    "Price change smoothing factor must be between 0 and 1 (exclusive)."
                )

        if not (
            Decimal("0")
            <= self.strategy.circuit_breaker.max_daily_loss_pct
            < Decimal("1")
        ):
            raise ConfigurationError(
                "max_daily_loss_pct must be between 0 and 1 (exclusive)."
            )

import logging
from collections import deque
import time # Added for TradingState

@dataclass(frozen=True)
class MarketInfo:
    symbol: str
    price_precision: Decimal
    quantity_precision: Decimal
    min_order_qty: Decimal
    min_notional_value: Decimal
    maker_fee_rate: Decimal = Decimal("0")
    taker_fee_rate: Decimal = Decimal("0")

    def format_price(self, p: Decimal) -> Decimal:
        return p.quantize(self.price_precision, rounding=ROUND_DOWN)

    def format_quantity(self, q: Decimal) -> Decimal:
        return q.quantize(self.quantity_precision, rounding=ROUND_DOWN)


@dataclass
class TradingState:
    mid_price: Decimal = Decimal("0")
    smoothed_mid_price: Decimal = Decimal("0")
    current_balance: Decimal = Decimal("0")
    available_balance: Decimal = Decimal("0")
    current_position_qty: Decimal = Decimal("0")
    unrealized_pnl_derivatives: Decimal = Decimal("0")

    active_orders: dict[str, dict] = field(default_factory=dict)
    last_order_management_time: float = 0.0
    last_ws_message_time: float = field(default_factory=time.time)
    last_status_report_time: float = 0.0
    last_health_check_time: float = 0.0

    price_candlestick_history: deque[tuple[float, Decimal, Decimal, Decimal]] = field(
        default_factory=deque
    )
    circuit_breaker_price_points: deque[tuple[float, Decimal]] = field(
        default_factory=deque
    )

    is_paused: bool = False
    pause_end_time: float = 0.0
    circuit_breaker_cooldown_end_time: float = 0.0
    ws_reconnect_attempts_left: int = 0

    metrics: TradeMetrics = field(default_factory=TradeMetrics)

    daily_initial_capital: Decimal = Decimal("0")
    daily_pnl_reset_date: datetime | None = None

    last_dry_run_price_update_time: float = field(default_factory=time.time)


def setup_logger(config: FilesConfig) -> logging.Logger:
    logger = logging.getLogger("MarketMakerBot")
    logger.setLevel(getattr(logging, config.log_level.upper()))
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        fh = logging.FileHandler(config.log_file)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    return logger