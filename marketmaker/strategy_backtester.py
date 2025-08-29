import logging
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
import numpy as np
import pandas as pd
import time # Added for time.time()

from backtest import FillEngine, BacktestParams # Import FillEngine and BacktestParams

from config_definitions import (
    Config,
    StrategyConfig,
    InventoryStrategyConfig,
    DynamicSpreadConfig,
    CircuitBreakerConfig,
    TradeMetrics,
    FilesConfig, # Needed for setup_logger
)
from config_definitions import MarketInfo, TradingState, setup_logger

# Use the same logger as the main bot for consistency
logger = logging.getLogger("MarketMakerBot")

class MarketMakingStrategy:
    def __init__(self, config: Config, market_info: MarketInfo):
        self.config = config
        self.market_info = market_info

    

    def _calculate_dynamic_spread(self, state: TradingState) -> Decimal:
        ds_config = self.config.strategy.dynamic_spread
        current_time = time.time() # In backtest, this will be simulated time

        # In backtest, we need to ensure price_candlestick_history is populated
        # This will be handled by the Backtester class
        relevant_candles = [
            c
            for c in state.price_candlestick_history
            if (current_time - c[0]) <= ds_config.volatility_window_sec
        ]

        if not ds_config.enabled or len(relevant_candles) < 2:
            return self.config.strategy.base_spread_pct

        true_ranges = []
        for i in range(len(relevant_candles)):
            ts, high, low, close = relevant_candles[i]

            if i == len(relevant_candles) - 1 and state.mid_price > Decimal("0"):
                close = state.mid_price

            if i == 0:
                tr = high - low
            else:
                _, _, _, prev_close = relevant_candles[i - 1]
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)

        if not true_ranges:
            return self.config.strategy.base_spread_pct

        atr_value = Decimal(str(np.mean([float(tr) for tr in true_ranges])))

        if state.mid_price <= Decimal("0"):
            logger.warning(
                "Mid-price is zero, cannot calculate ATR-based spread. Using base spread."
            )
            return self.config.strategy.base_spread_pct

        volatility_pct = atr_value / state.mid_price

        dynamic_adjustment = volatility_pct * ds_config.volatility_multiplier
        clamped_spread = max(
            ds_config.min_spread_pct,
            min(
                ds_config.max_spread_pct,
                self.config.strategy.base_spread_pct + dynamic_adjustment,
            ),
        )
        logger.debug(
            f"ATR: {atr_value:.6f}, Volatility_pct: {volatility_pct:.6f}, Dynamic Spread: {clamped_spread:.4%}"
        )
        return clamped_spread

    def _calculate_inventory_skew(
        self, mid_price: Decimal, pos_qty: Decimal
    ) -> Decimal:
        inv_config = self.config.strategy.inventory
        if (
            not inv_config.enabled
            or self.config.max_net_exposure_usd <= 0
            or mid_price <= 0
        ):
            return Decimal("0")

        current_inventory_value = pos_qty * mid_price
        max_exposure_for_ratio = (
            self.config.max_net_exposure_usd * inv_config.max_inventory_ratio
        )
        if max_exposure_for_ratio <= 0:
            return Decimal("0")

        inventory_ratio = current_inventory_value / max_exposure_for_ratio
        inventory_ratio = max(Decimal("-1.0"), min(Decimal("1.0"), inventory_ratio))

        skew_factor = -inventory_ratio * inv_config.skew_intensity

        if abs(skew_factor) > Decimal("1e-6"):
            logger.debug(
                f"Inventory skew active. Position Value: {current_inventory_value:.2f} {self.config.quote_currency}, Ratio: {inventory_ratio:.3f}, Skew: {skew_factor:.6f}"
            )
        return skew_factor

    def _enforce_min_profit_spread(
        self, mid_price: Decimal, bid_p: Decimal, ask_p: Decimal
    ) -> tuple[Decimal, Decimal]:
        if not self.market_info or mid_price <= Decimal("0"):
            logger.warning(
                "Mid-price or market info not available for enforcing minimum profit spread. Returning original bid/ask."
            )
            return bid_p, ask_p

        estimated_fee_per_side_pct = self.market_info.taker_fee_rate
        min_gross_spread_pct = self.config.strategy.min_profit_spread_after_fees_pct + (
            estimated_fee_per_side_pct * Decimal("2")
        )
        min_spread_val = mid_price * min_gross_spread_pct

        if ask_p <= bid_p or (ask_p - bid_p) < min_spread_val:
            logger.debug(
                f"Adjusting spread. Original Bid: {bid_p}, Ask: {ask_p}, Mid: {mid_price}, Current Spread: {ask_p - bid_p:.6f}, Min Spread: {min_spread_val:.6f}"
            )
            half_min_spread = (min_spread_val / Decimal("2")).quantize(
                self.market_info.price_precision
            )
            bid_p = (mid_price - half_min_spread).quantize(
                self.market_info.price_precision
            )
            ask_p = (mid_price + half_min_spread).quantize(
                self.market_info.price_precision
            )
            logger.debug(f"Adjusted to Bid: {bid_p}, Ask: {ask_p}")
        return bid_p, ask_p

    def _calculate_order_size(self, side: str, price: Decimal, state: TradingState) -> Decimal:
        capital = (
            state.available_balance
            if self.config.category == "spot"
            else state.current_balance
        )
        metrics_pos_qty = state.metrics.current_asset_holdings

        if capital <= Decimal("0") or price <= Decimal("0") or not self.market_info:
            logger.debug(
                "Insufficient capital, zero price, or no market info. Order size 0."
            )
            return Decimal("0")

        effective_capital = (
            capital * self.config.leverage
            if self.config.category in ["linear", "inverse"]
            else capital
        )

        base_order_value = (
            effective_capital * self.config.strategy.base_order_size_pct_of_balance
        )
        qty_from_base_pct = base_order_value / price

        max_order_value_abs = effective_capital * self.config.max_order_size_pct
        qty_from_max_pct = max_order_value_abs / price

        target_qty = min(qty_from_base_pct, qty_from_max_pct)

        if (
            self.config.strategy.inventory.enabled
            and self.config.max_net_exposure_usd > Decimal("0")
        ):
            current_mid_price = state.mid_price # Use state's mid_price
            if current_mid_price == Decimal("0"):
                logger.warning(
                    "Mid-price is zero, cannot calculate max net exposure. Skipping exposure check."
                )
                return Decimal("0")

            max_allowed_pos_qty_abs = (
                self.config.max_net_exposure_usd / current_mid_price
            )

            if side == "Buy":
                qty_to_reach_max_long = max_allowed_pos_qty_abs - metrics_pos_qty
                if qty_to_reach_max_long <= Decimal("0"):
                    logger.debug(
                        f"Cannot place buy order: Current position {metrics_pos_qty} already at or above max long exposure ({max_allowed_pos_qty_abs})."
                    )
                    return Decimal("0")
                target_qty = min(target_qty, qty_to_reach_max_long)
            else:
                if metrics_pos_qty > Decimal("0"):
                    target_qty = min(target_qty, metrics_pos_qty)
                    logger.debug(
                        f"Capping sell order quantity at current holdings: {target_qty}"
                    )
                else:
                    qty_to_reach_max_short = -max_allowed_pos_qty_abs - metrics_pos_qty
                    if qty_to_reach_max_short >= Decimal("0"):
                        logger.debug(
                            f"Cannot place sell order: Current position {metrics_pos_qty} already at or below max short exposure ({-max_allowed_pos_qty_abs})."
                        )
                        return Decimal("0")
                    target_qty = min(target_qty, abs(qty_to_reach_max_short))

        if target_qty <= Decimal("0"):
            logger.debug(
                "Calculated target quantity is zero or negative after exposure adjustments. Order size 0."
            )
            return Decimal("0")

        qty = self.market_info.format_quantity(target_qty)

        if qty < self.market_info.min_order_qty:
            logger.debug(
                f"Calculated quantity {qty} is less than min_order_qty {self.market_info.min_order_qty}. Order size 0."
            )
            return Decimal("0")

        order_notional_value = qty * price
        min_notional = max(
            self.market_info.min_notional_value, self.config.min_order_value_usd
        )
        if order_notional_value < min_notional:
            logger.debug(
                f"Calculated notional value {order_notional_value:.2f} is less than min_notional_value {min_notional:.2f}. Order size 0."
            )
            return Decimal("0")

        logger.debug(
            f"Calculated {side} order size: {qty} {self.config.base_currency} (Notional: {order_notional_value:.2f} {self.config.quote_currency})"
        )
        return qty

    def get_target_orders(self, state: TradingState, orderbook_data: dict = None) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        # This combines logic from _manage_orders to determine target prices and quantities
        mid_price_for_strategy = state.smoothed_mid_price
        pos_qty = state.metrics.current_asset_holdings

        

        spread_pct = self._calculate_dynamic_spread(state)

        skew_factor = self._calculate_inventory_skew(mid_price_for_strategy, pos_qty)
        skewed_mid_price = mid_price_for_strategy * (Decimal("1") + skew_factor)

        target_bid_price = skewed_mid_price * (Decimal("1") - spread_pct)
        target_ask_price = skewed_mid_price * (Decimal("1") + spread_pct)
        target_bid_price, target_ask_price = self._enforce_min_profit_spread(
            mid_price_for_strategy, target_bid_price, target_ask_price
        )

        target_bid_price = self.market_info.format_price(target_bid_price)
        target_ask_price = self.market_info.format_price(target_ask_price)

        

        buy_qty = self._calculate_order_size("Buy", target_bid_price, state)
        sell_qty = self._calculate_order_size("Sell", target_ask_price, state)

        return target_bid_price, buy_qty, target_ask_price, sell_qty

class Backtester:
    def __init__(self, config: Config, klines_df: pd.DataFrame, kline_interval: str, initial_capital: Decimal = Decimal("10000")):
        self.config = config
        self.klines_df = klines_df
        self.initial_capital = initial_capital

        # Initialize MarketInfo for backtesting
        self.market_info = MarketInfo(
            symbol=self.config.symbol,
            price_precision=Decimal("0.00001"), # Default for XLMUSDT
            quantity_precision=Decimal("1"),    # Default for XLMUSDT
            min_order_qty=Decimal("1"),         # Default for XLMUSDT
            min_notional_value=self.config.min_order_value_usd,
            maker_fee_rate=Decimal("0.0002"),
            taker_fee_rate=Decimal("0.0005"),
        )
        # Override with actual market info if available (e.g., from a pre-fetched source)
        # For now, use hardcoded defaults or pass from outside if needed.

        self.strategy = MarketMakingStrategy(self.config, self.market_info)
        self.state = TradingState(
            current_balance=initial_capital,
            available_balance=initial_capital,
            daily_initial_capital=initial_capital,
            daily_pnl_reset_date=datetime.fromtimestamp(klines_df['start'].iloc[0] / 1000, tz=timezone.utc),
            price_candlestick_history=deque(maxlen=self.config.strategy.dynamic_spread.volatility_window_sec + 1),
            circuit_breaker_price_points=deque(maxlen=self.config.strategy.circuit_breaker.check_window_sec * 2),
        )
        self.logger = setup_logger(self.config.files) # Re-initialize logger for backtester

        # Create a minimal BacktestParams for FillEngine
        fill_engine_params = BacktestParams(
            symbol=self.config.symbol,
            category=self.config.category,
            interval=kline_interval, # Use the passed kline_interval
            start=datetime.fromtimestamp(klines_df['start'].iloc[0] / 1000, tz=timezone.utc),
            end=datetime.fromtimestamp(klines_df['start'].iloc[-1] / 1000, tz=timezone.utc),
            maker_fee=float(self.market_info.maker_fee_rate), # Convert Decimal to float
            # fill_on_touch, volume_cap_ratio, rng_seed, sl_tp_emulation are defaults in BacktestParams
        )
        self.fill_engine = FillEngine(fill_engine_params)

        self.equity_curve: list[tuple[int, Decimal]] = [] # (timestamp ms, equity)
        self.trades: list[dict] = [] # Simulated trades

    def run(self) -> dict:
        logger.info(f"Starting backtest for {self.config.symbol} from {datetime.fromtimestamp(self.klines_df['start'].iloc[0]/1000)} to {datetime.fromtimestamp(self.klines_df['start'].iloc[-1]/1000)}")

        for index, row in self.klines_df.iterrows():
            current_timestamp_ms = int(row['start'])
            current_timestamp_dt = datetime.fromtimestamp(current_timestamp_ms / 1000, tz=timezone.utc)
            current_price = Decimal(str(row['close'])) # Use close price as current mid for simplicity

            # Update state with current market data
            self.state.mid_price = current_price
            self.state.smoothed_mid_price = current_price # For simplicity in backtest, can be refined
            self.state.price_candlestick_history.append((current_timestamp_ms / 1000, Decimal(str(row['high'])), Decimal(str(row['low'])), current_price))
            self.state.circuit_breaker_price_points.append((current_timestamp_ms / 1000, current_price))

            # Simulate order management
            target_bid_price, buy_qty, target_ask_price, sell_qty = self.strategy.get_target_orders(self.state)

            logger.debug(f"Timestamp: {current_timestamp_dt}, Mid: {self.state.mid_price}, Smoothed Mid: {self.state.smoothed_mid_price}")
            logger.debug(f"Target Bid: {target_bid_price}, Buy Qty: {buy_qty}")
            logger.debug(f"Target Ask: {target_ask_price}, Sell Qty: {sell_qty}")

            # Simulate fills using intra-bar path and volume capacity
            o, h, l, c = float(row['open']), float(row['high']), float(row['low']), float(row['close'])
            ts_ms = int(row['start'])
            path = self._intrabar_path(o, h, l, c, ts_ms)
            logger.debug(f"Candle Path: {path}, Candle Volume: {row['volume']})")

            capacity_remaining = self._volume_capacity(float(row['volume']))

            # Simulate fills for buy orders
            if buy_qty > 0 and capacity_remaining > 0:
                # Check if target_bid_price is touched by the intra-bar path
                if min(path) <= float(target_bid_price):
                    fill_size = min(float(buy_qty), capacity_remaining)
                    self._simulate_fill("Buy", Decimal(str(fill_size)), target_bid_price, current_timestamp_dt)
                    capacity_remaining -= fill_size

            # Simulate fills for sell orders
            if sell_qty > 0 and capacity_remaining > 0:
                # Check if target_ask_price is touched by the intra-bar path
                if max(path) >= float(target_ask_price):
                    fill_size = min(float(sell_qty), capacity_remaining)
                    self._simulate_fill("Sell", Decimal(str(fill_size)), target_ask_price, current_timestamp_dt)
                    capacity_remaining -= fill_size

            # Update equity curve
            equity = self.state.metrics.net_realized_pnl + self.state.metrics.calculate_unrealized_pnl(current_price)
            self.equity_curve.append((current_timestamp_ms, equity))

        # Calculate final metrics
        equity_series = pd.Series([e for (_, e) in self.equity_curve])
        returns = equity_series.diff().fillna(0.0)
        sharpe = self._calc_sharpe(returns.values)
        total_return = float(equity_series.iloc[-1]) if len(equity_series) > 0 else 0.0
        max_dd = self._max_drawdown([float(e) for (_, e) in self.equity_curve])

        results = {
            "net_pnl": round(total_return, 6),
            "max_drawdown": round(max_dd, 6),
            "sharpe_like": round(sharpe, 4),
            "final_position": float(self.state.metrics.current_asset_holdings),
        }
        logger.info(f"Backtest complete. Results: {results}")
        return results

    def _simulate_fill(self, side: str, qty: Decimal, price: Decimal, timestamp: datetime):
        logger.debug(f"Simulating {side} fill: Qty={qty}, Price={price}")
        exec_fee = qty * price * self.market_info.taker_fee_rate # Assume taker fill for simplicity

        metrics = self.state.metrics
        realized_pnl_impact = Decimal("0")

        # Calculate realized_pnl_impact before updating position
        if side == "Sell" and metrics.current_asset_holdings > 0:
            # Only calculate profit/loss on sale if we are closing a long position
            realized_pnl_impact = (price - metrics.average_entry_price) * qty
        elif side == "Buy" and metrics.current_asset_holdings < 0:
            # Only calculate profit/loss on sale if we are closing a short position
            realized_pnl_impact = (metrics.average_entry_price - price) * qty

        # Update position and PnL using the new method
        metrics.update_position_and_pnl(side, qty, price)
        
        # Update balance based on fill
        if side == "Buy":
            self.state.current_balance -= (qty * price) + exec_fee
        elif side == "Sell":
            self.state.current_balance += (qty * price) - exec_fee
        self.state.available_balance = self.state.current_balance # Assuming all balance is available

        metrics.total_fees += exec_fee # Add fee to total fees

        self.trades.append({
            "timestamp": timestamp.isoformat(),
            "side": side,
            "qty": float(qty),
            "price": float(price),
            "fee": float(exec_fee),
            "realized_pnl_impact": float(realized_pnl_impact),
            "net_realized_pnl": float(metrics.net_realized_pnl),
            "current_asset_holdings": float(metrics.current_asset_holdings),
            "average_entry_price": float(metrics.average_entry_price),
        })

    def _intrabar_path(self, o: float, h: float, low_price: float, c: float, ts_ms: int) -> list[float]:
        """
        Generate a simple deterministic intra-candle path: open -> mid-extreme ->
        other extreme -> close. The ordering (O-H-L-C) vs (O-L-H-C) is seeded by
        timestamp for variety but reproducibility.
        """
        # Use self.params.rng_seed if BacktestParams is available, otherwise use a fixed seed
        # For now, let's use a fixed seed.
        rnd = (ts_ms // 60000) ^ 42 # Using a fixed seed for now
        go_high_first = rnd % 2 == 0
        if go_high_first:
            return [o, (o + h) / 2, h, (h + low_price) / 2, low_price, (low_price + c) / 2, c]
        else:
            return [o, (o + low_price) / 2, low_price, (low_price + h) / 2, h, (h + c) / 2, c]

    def _volume_capacity(self, candle_volume: float) -> float:
        """
        Simplistic capacity: only a fraction of the candle's volume is available
        to our maker orders. Interpreting 'volume' as contract or base-asset
        volume depending on market; adjust as needed.
        """
        # The original FillEngine takes params.volume_cap_ratio.
        # For now, I'll use a fixed ratio.
        return max(0.0, candle_volume) * 0.25 # Using a fixed ratio for now

    @staticmethod
    def _calc_sharpe(step_pnl: np.ndarray) -> float:
        # Convert Decimal objects to float before numpy operations
        step_pnl_float = np.array([float(x) for x in step_pnl])
        if len(step_pnl_float) < 2:
            return 0.0
        mu = np.mean(step_pnl_float)
        sd = np.std(step_pnl_float)
        if sd == 0:
            return 0.0
        return float(mu / sd)

    @staticmethod
    def _max_drawdown(equity: list[float]) -> float:
        peak = -float("inf")
        max_dd = 0.0
        for e in equity:
            if e > peak:
                peak = e
            dd = peak - e
            if dd > max_dd:
                max_dd = dd
        return max_dd
