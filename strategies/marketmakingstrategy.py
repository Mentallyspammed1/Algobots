from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
from algobots_types import OrderBlock  # Assuming this is available
from colorama import Fore, Style, init

from .strategy_template import StrategyTemplate

init()  # Initialize Colorama for vibrant terminal output


class MarketMakingStrategy(StrategyTemplate):
    """An enhanced, adaptive market making strategy with ATR-based dynamic spreads,
    inventory-aware skewing, S/R and Order Block avoidance, dynamic stop-loss,
    and improved hedging and logging for Termux compatibility.
    """

    def __init__(
        self,
        logger,
        spread_bps: int = 20,  # Base spread in BPS
        # --- Size & Position ---
        use_volatility_adjusted_size: bool = True,
        base_order_quantity: Decimal = Decimal("0.01"),
        volatility_sensitivity: Decimal = Decimal("0.5"),
        max_position_size: Decimal = Decimal("0.05"),
        max_order_quantity: Decimal = Decimal("0.1"),  # NEW: Max individual order size
        # --- Skew & Spread ---
        use_dynamic_spread: bool = True,
        atr_spread_multiplier: Decimal = Decimal("0.5"),
        inventory_skew_intensity: Decimal = Decimal("5.0"),
        # --- Trend & S/R ---
        use_trend_filter: bool = True,
        sr_level_avoidance_bps: int = 2,
        use_order_block_logic: bool = True,
        ob_avoidance_bps: int = 1,
        # --- Risk Management ---
        rebalance_threshold: Decimal = Decimal("0.03"),
        rebalance_aggressiveness: str = "MARKET",
        use_dynamic_stop_loss: bool = True,
        stop_loss_atr_multiplier: Decimal = Decimal("2.5"),
        # --- New Parameters (from previous analysis, now integrated) ---
        hedge_ratio: Decimal = Decimal("0.2"),  # Hedge 20% of position
        max_spread_bps: int = 50,  # Cap for dynamic spread
        min_order_quantity: Decimal = Decimal("0.005"),  # Minimum order size
        # --- New Upgrades Parameters ---
        hedge_cooldown_s: int = 60,  # Cooldown for hedging in seconds
        rebalance_fraction: Decimal = Decimal(
            "1.0",
        ),  # Fraction of position to rebalance
        simulate: bool = False,  # Wet-run flag
        max_signals_per_cycle: int = 5,  # Cap on signals per cycle
        max_data_age_s: int = 30,  # Max age of data before skipping cycle
    ):
        super().__init__(logger)
        # Assign parameters with type conversion and direct calculation
        self.spread_bps = Decimal(str(spread_bps))  # Base spread in BPS
        self.use_volatility_adjusted_size = use_volatility_adjusted_size
        self.base_order_quantity = base_order_quantity
        self.volatility_sensitivity = volatility_sensitivity
        self.max_position_size = max_position_size
        self.max_order_quantity = max_order_quantity  # Assign new parameter
        self.use_dynamic_spread = use_dynamic_spread
        self.atr_spread_multiplier = atr_spread_multiplier
        self.inventory_skew_intensity = inventory_skew_intensity
        self.use_trend_filter = use_trend_filter
        # Convert BPS to decimal percentage once here
        self.sr_level_avoidance_pct = self._bps_to_pct(
            Decimal(str(sr_level_avoidance_bps)),
        )
        self.use_order_block_logic = use_order_block_logic
        # Convert BPS to decimal percentage once here
        self.ob_avoidance_pct = self._bps_to_pct(Decimal(str(ob_avoidance_bps)))
        self.rebalance_threshold = rebalance_threshold
        self.rebalance_aggressiveness = rebalance_aggressiveness
        self.use_dynamic_stop_loss = use_dynamic_stop_loss
        self.stop_loss_atr_multiplier = stop_loss_atr_multiplier
        self.hedge_ratio = hedge_ratio
        self.max_spread_bps = Decimal(str(max_spread_bps))
        self.min_order_quantity = min_order_quantity

        # --- New Upgrades Assignments ---
        self.hedge_cooldown_s = hedge_cooldown_s
        self._last_hedge_time = datetime.utcnow() - timedelta(
            seconds=hedge_cooldown_s * 2,
        )  # Initialize to allow immediate hedging
        self.rebalance_fraction = rebalance_fraction
        self.simulate = simulate
        self.max_signals_per_cycle = max_signals_per_cycle
        self.max_data_age_s = max_data_age_s
        self.loss_count = 0
        self.win_count = 0

        # --- Validation ---
        if self.rebalance_threshold > self.max_position_size:
            self.logger.warning(
                Fore.YELLOW
                + f"Rebalance threshold ({self.rebalance_threshold}) exceeds max position size ({self.max_position_size}). Adjusting to {self.max_position_size}."
                + Style.RESET_ALL,
            )
            self.rebalance_threshold = self.max_position_size
        if self.rebalance_aggressiveness not in ["MARKET", "AGGRESSIVE_LIMIT"]:
            self.logger.warning(
                Fore.YELLOW
                + f"Invalid rebalance_aggressiveness '{self.rebalance_aggressiveness}'. Defaulting to 'MARKET'."
                + Style.RESET_ALL,
            )
            self.rebalance_aggressiveness = "MARKET"
        if self.min_order_quantity <= 0:
            self.logger.warning(
                Fore.YELLOW
                + f"Min order quantity must be positive. Setting to {self.base_order_quantity / 2 if self.base_order_quantity > 0 else Decimal('0.0001')}."
                + Style.RESET_ALL,
            )
            self.min_order_quantity = (
                self.base_order_quantity / 2
                if self.base_order_quantity > 0
                else Decimal("0.0001")
            )
        if self.max_order_quantity <= self.min_order_quantity:
            self.logger.warning(
                Fore.YELLOW
                + f"Max order quantity ({self.max_order_quantity}) must be greater than min order quantity ({self.min_order_quantity}). Setting max to {self.min_order_quantity * 2}."
                + Style.RESET_ALL,
            )
            self.max_order_quantity = (
                self.min_order_quantity * 2
                if self.min_order_quantity > 0
                else Decimal("0.0002")
            )
        if (
            self.base_order_quantity < self.min_order_quantity
            or self.base_order_quantity > self.max_order_quantity
        ):
            self.logger.warning(
                Fore.YELLOW
                + f"Base order quantity ({self.base_order_quantity}) is outside min/max order quantity range. Adjusting to be within bounds."
                + Style.RESET_ALL,
            )
            self.base_order_quantity = max(
                self.min_order_quantity,
                min(self.base_order_quantity, self.max_order_quantity),
            )
        if self.hedge_ratio < 0 or self.hedge_ratio > 1:
            self.logger.warning(
                Fore.YELLOW
                + f"Hedge ratio ({self.hedge_ratio}) must be between 0 and 1. Defaulting to 0.2."
                + Style.RESET_ALL,
            )
            self.hedge_ratio = Decimal("0.2")

        self.logger.info(
            Fore.CYAN + "Summoning Enhanced MarketMakingStrategy..." + Style.RESET_ALL,
        )

    def _bps_to_pct(self, bps: Decimal) -> Decimal:
        """Converts basis points to a decimal percentage."""
        return bps / Decimal("10000")

    def _calculate_volatility_adjusted_size(
        self, latest_atr: Decimal, current_price: Decimal,
    ) -> Decimal:
        """Calculate order size adjusted for volatility, with a minimum and maximum size cap."""
        if (
            not self.use_volatility_adjusted_size
            or latest_atr <= 0
            or current_price <= 0
        ):
            self.logger.debug(
                Fore.YELLOW
                + f"Volatility adjustment disabled or invalid data. Using base order quantity: {self.base_order_quantity}"
                + Style.RESET_ALL,
            )
            return self.base_order_quantity

        # Normalize ATR as a percentage of price
        normalized_atr = latest_atr / current_price
        # Dampen volatility effect with smoother scaling
        size_multiplier = Decimal("1") / (
            Decimal("1") + normalized_atr * self.volatility_sensitivity
        )

        # Apply min/max caps
        adjusted_size = self.base_order_quantity * size_multiplier
        adjusted_size = max(self.min_order_quantity, adjusted_size)
        adjusted_size = min(self.max_order_quantity, adjusted_size)  # Apply max cap

        self.logger.debug(
            Fore.GREEN
            + f"Volatility-Adjusted Size: {adjusted_size:.4f} (Base: {self.base_order_quantity}, Multiplier: {size_multiplier:.4f})"
            + Style.RESET_ALL,
        )
        return adjusted_size

    def _calculate_hedge_size(self, current_position_size: Decimal) -> Decimal:
        """Calculate hedge order size based on position size, respecting min_order_quantity."""
        hedge_size = current_position_size * self.hedge_ratio
        if hedge_size < self.min_order_quantity:
            self.logger.debug(
                Fore.YELLOW
                + f"Calculated hedge size {hedge_size:.4f} is below min_order_quantity {self.min_order_quantity:.4f}. Not hedging."
                + Style.RESET_ALL,
            )
            return Decimal("0")  # Don't hedge if size is too small

        self.logger.debug(
            Fore.CYAN
            + f"Hedging {hedge_size:.4f} of position {current_position_size}."
            + Style.RESET_ALL,
        )
        return min(hedge_size, self.max_position_size)

    def generate_signals(
        self,
        df: pd.DataFrame,
        resistance_levels: list[dict[str, Any]],
        support_levels: list[dict[str, Any]],
        active_bull_obs: list[OrderBlock],
        active_bear_obs: list[OrderBlock],
        **kwargs,
    ) -> list[tuple[str, Decimal, Any, dict[str, Any]]]:
        """Generate market making signals with dynamic spreads and hedging."""
        signals = []
        signals_generated_this_cycle = 0

        required_cols = ["close", "atr", "ehlers_supersmoother"]
        if df.empty or not all(col in df.columns for col in required_cols):
            self.logger.warning(
                Fore.RED
                + f"DataFrame missing required columns: {required_cols}. Cannot generate signals."
                + Style.RESET_ALL,
            )
            return []

        # --- Extract Data ---
        latest_candle = df.iloc[-1]

        current_price_val = latest_candle["close"]
        latest_atr_val = latest_candle["atr"]
        ehlers_supersmoother_val = latest_candle["ehlers_supersmoother"]

        if (
            pd.isna(current_price_val)
            or pd.isna(latest_atr_val)
            or pd.isna(ehlers_supersmoother_val)
        ):
            self.logger.warning(
                Fore.RED
                + "Critical indicator values (close, atr, ehlers_supersmoother) are NaN. Cannot generate signals."
                + Style.RESET_ALL,
            )
            return []

        current_price = Decimal(str(current_price_val))
        latest_atr = Decimal(str(latest_atr_val))
        timestamp = df.index[-1]

        # Upgrade 9: Add defense against stale data
        now_utc = datetime.utcnow().replace(tzinfo=None)
        if now_utc - timestamp.to_pydatetime().replace(tzinfo=None) > timedelta(
            seconds=self.max_data_age_s,
        ):
            self.logger.warning(
                Fore.YELLOW + "Data is stale. Skipping cycle." + Style.RESET_ALL,
            )
            return []

        current_position_side = kwargs.get("current_position_side", "NONE")
        current_position_size = Decimal(str(kwargs.get("current_position_size", "0")))
        signed_inventory = (
            current_position_size
            if current_position_side == "LONG"
            else -current_position_size
            if current_position_side == "SHORT"
            else Decimal("0")
        )

        # Upgrade 7: Mid-cycle parameter refresh (placeholder)
        # await self._refresh_params() # Uncomment and implement _refresh_params if needed

        # --- Calculate Dynamic Order Size ---
        order_quantity = self._calculate_volatility_adjusted_size(
            latest_atr, current_price,
        )
        # Upgrade 3: Additional Check for Order Quantity
        if order_quantity <= 0:  # Ensure order quantity is valid
            self.logger.warning(
                Fore.RED
                + "Calculated order quantity is zero or less. Skipping signal generation."
                + Style.RESET_ALL,
            )
            return []

        # --- Dynamic Spread with Cap ---
        dynamic_spread_bps = self.spread_bps  # Start with base spread
        if self.use_dynamic_spread and current_price > 0:
            # atr_spread_adj is calculated in BPS (latest_atr / current_price is a percentage)
            atr_spread_adj = (
                (latest_atr / current_price)
                * self.atr_spread_multiplier
                * Decimal("10000")
            )
            dynamic_spread_bps = min(
                self.max_spread_bps, self.spread_bps + atr_spread_adj,
            )
            # Upgrade 2: Improved Logging for Dynamic Spread
            self.logger.debug(
                Fore.BLUE
                + f"Dynamic spread adjusted from {self.spread_bps} to {dynamic_spread_bps:.2f} bps due to ATR."
                + Style.RESET_ALL,
            )

        # --- Trend Filter & Skew ---
        skewed_mid_price = current_price
        # Upgrade 4: Refactored Trend Filter Logic
        if self.use_trend_filter:
            trend_ma = Decimal(str(latest_candle["ehlers_supersmoother"]))
            trend_direction = (
                "Uptrend"
                if current_price > trend_ma
                else "Downtrend"
                if current_price < trend_ma
                else "Neutral"
            )

            # Using inventory_skew_intensity for trend skew as per original code, can be separated later
            trend_skew_factor = self.inventory_skew_intensity / Decimal(
                "10000",
            )  # This is still a percentage
            if trend_direction == "Uptrend":
                skewed_mid_price *= (
                    Decimal("1") + trend_skew_factor
                )  # Skew mid price higher in uptrend
            elif trend_direction == "Downtrend":
                skewed_mid_price *= (
                    Decimal("1") - trend_skew_factor
                )  # Skew mid price lower in downtrend
            # else neutral, no skew from trend
            self.logger.debug(
                Fore.MAGENTA
                + f"Trend: {trend_direction}, Skewed Mid Price (after trend): {skewed_mid_price:.8f}"
                + Style.RESET_ALL,
            )

        # --- Inventory Skew ---
        if self.max_position_size > 0:
            # inventory_ratio: positive if long, negative if short
            inventory_ratio = signed_inventory / self.max_position_size
            # Inventory skew: positive if we are too long, negative if too short
            # If long, reduce bid price (to discourage more buys), increase ask price (to encourage sells)
            # If short, increase bid price (to encourage buys), reduce ask price (to discourage more sells)
            inventory_skew_adjustment = (
                current_price * self.inventory_skew_intensity / Decimal("10000")
            ) * inventory_ratio
            skewed_mid_price -= inventory_skew_adjustment  # Subtract if long (positive adjustment), add if short (negative adjustment)

            self.logger.debug(
                Fore.YELLOW
                + f"Signed Inventory: {signed_inventory:.4f}, Inventory Ratio: {inventory_ratio:.4f}, Inventory Skew Adjustment: {inventory_skew_adjustment:.8f}, Adjusted Mid Price (after inventory): {skewed_mid_price:.8f}"
                + Style.RESET_ALL,
            )

        # --- Calculate Bid/Ask from skewed mid price ---
        # Spread factor is dynamic_spread_bps / 20000 (bps / 2 for half spread / 10000 for percentage)
        spread_factor = dynamic_spread_bps / Decimal("20000")
        bid_price = skewed_mid_price * (Decimal("1") - spread_factor)
        ask_price = skewed_mid_price * (Decimal("1") + spread_factor)

        # --- S/R and Order Block Avoidance ---
        all_support = [Decimal(str(lvl["price"])) for lvl in support_levels] + [
            Decimal(str(ob["top"]))
            for ob in active_bull_obs
            if self.use_order_block_logic
        ]
        all_resistance = [Decimal(str(lvl["price"])) for lvl in resistance_levels] + [
            Decimal(str(ob["bottom"]))
            for ob in active_bear_obs
            if self.use_order_block_logic
        ]

        # Sort levels to process closest first for cascading adjustments
        all_support.sort(reverse=True)  # Check higher supports first for bid adjustment
        all_resistance.sort()  # Check lower resistances first for ask adjustment

        # Upgrade 5: Efficient S/R and Order Block Avoidance
        for s_lvl in all_support:
            if bid_price >= s_lvl and bid_price < s_lvl * (
                Decimal("1") + self.sr_level_avoidance_pct
            ):
                adjustment_amount = s_lvl * self.sr_level_avoidance_pct
                bid_price = s_lvl - adjustment_amount
                self.logger.debug(
                    Fore.CYAN
                    + f"Adjusted BID to {bid_price:.8f} to avoid support/OB at {s_lvl:.8f}"
                    + Style.RESET_ALL,
                )

        for r_lvl in all_resistance:
            if ask_price <= r_lvl and ask_price > r_lvl * (
                Decimal("1") - self.sr_level_avoidance_pct
            ):
                adjustment_amount = r_lvl * self.sr_level_avoidance_pct
                ask_price = r_lvl + adjustment_amount
                self.logger.debug(
                    Fore.CYAN
                    + f"Adjusted ASK to {ask_price:.8f} to avoid resistance/OB at {r_lvl:.8f}"
                    + Style.RESET_ALL,
                )

        # Ensure bid is always below ask
        if bid_price >= ask_price:
            avg_price = (bid_price + ask_price) / Decimal("2")
            bid_price = avg_price * (
                Decimal("1") - self._bps_to_pct(self.spread_bps / Decimal("2"))
            )  # Re-apply base spread if needed
            ask_price = avg_price * (
                Decimal("1") + self._bps_to_pct(self.spread_bps / Decimal("2"))
            )
            self.logger.warning(
                Fore.RED
                + f"Bid {bid_price:.8f} was >= Ask {ask_price:.8f} after adjustments. Re-adjusted prices."
                + Style.RESET_ALL,
            )

        # --- Hedging Logic ---
        # Upgrade 2: Cooldown between hedges
        if datetime.utcnow() - self._last_hedge_time < timedelta(
            seconds=self.hedge_cooldown_s,
        ):
            self.logger.info(
                Fore.YELLOW
                + f"Skipping hedge: Cooldown active. Next hedge in {self.hedge_cooldown_s - (datetime.utcnow() - self._last_hedge_time).total_seconds():.2f}s."
                + Style.RESET_ALL,
            )
        else:
            # Upgrade 6: Advanced Hedge Size Calculation
            hedge_quantity = self._calculate_hedge_size(abs(signed_inventory))
            if (
                hedge_quantity > self.min_order_quantity
            ):  # Only create hedge if quantity is meaningful
                hedge_side = (
                    "SELL" if signed_inventory > 0 else "BUY"
                )  # If currently long, sell to hedge; if short, buy to hedge
                hedge_order_type = (
                    "MARKET"  # Always use market for rebalancing/hedging for certainty
                )
                hedge_price = current_price  # For market orders, price is indicative

                # Upgrade 5: Wet-run flag
                if not self.simulate:
                    signals.append(
                        (
                            f"{hedge_side}_{hedge_order_type}",
                            hedge_price,
                            timestamp,
                            {
                                "order_type": hedge_order_type,
                                "quantity": hedge_quantity,
                                "strategy_id": "MM_HEDGE",
                                "created_at": datetime.utcnow(),
                            },
                        ),
                    )  # Upgrade 1: Add timestamp
                    self.logger.info(
                        Fore.YELLOW
                        + f"Initiating Hedge: Side={hedge_side}, Qty={hedge_quantity:.4f}, Current Inventory={signed_inventory:.4f}"
                        + Style.RESET_ALL,
                    )
                    self._last_hedge_time = (
                        datetime.utcnow()
                    )  # Upgrade 2: Update last hedge time
                    signals_generated_this_cycle += 1
                    if signals_generated_this_cycle >= self.max_signals_per_cycle:
                        return signals  # Upgrade 6: Cap signals
                else:
                    self.logger.debug(
                        Fore.BLUE
                        + f"Simulated Hedge: Side={hedge_side}, Qty={hedge_quantity:.4f}, Current Inventory={signed_inventory:.4f}"
                        + Style.RESET_ALL,
                    )

        # --- Final Signal Generation for Bid/Ask (main market making) ---
        # Ensure we don't exceed max position size with new orders
        # If position is too large on buy side, don't place new buy
        if (
            current_position_side == "LONG"
            and (current_position_size + order_quantity) > self.max_position_size
        ):
            self.logger.info(
                Fore.YELLOW
                + f"Skipping BUY signal: Max position size ({self.max_position_size}) would be exceeded. Current: {current_position_size}, Order: {order_quantity}"
                + Style.RESET_ALL,
            )
        elif (
            bid_price > 0 and order_quantity >= self.min_order_quantity
        ):  # Ensure valid price and quantity
            # Upgrade 5: Wet-run flag
            if not self.simulate:
                signals.append(
                    (
                        "BUY_LIMIT",
                        bid_price,
                        timestamp,
                        {
                            "order_type": "LIMIT",
                            "quantity": order_quantity,
                            "strategy_id": "MM_BID",
                            "created_at": datetime.utcnow(),
                        },
                    ),
                )  # Upgrade 1: Add timestamp
                self.logger.info(
                    Fore.GREEN
                    + f"Generated BUY LIMIT signal @ {bid_price:.8f}, Qty: {order_quantity:.4f}"
                    + Style.RESET_ALL,
                )
                signals_generated_this_cycle += 1
                if signals_generated_this_cycle >= self.max_signals_per_cycle:
                    return signals  # Upgrade 6: Cap signals
            else:
                self.logger.debug(
                    Fore.BLUE
                    + f"Simulated BUY LIMIT signal @ {bid_price:.8f}, Qty: {order_quantity:.4f}"
                    + Style.RESET_ALL,
                )

        # If position is too large on sell side, don't place new sell
        if (
            current_position_side == "SHORT"
            and (current_position_size + order_quantity) > self.max_position_size
        ):
            self.logger.info(
                Fore.YELLOW
                + f"Skipping SELL signal: Max position size ({self.max_position_size}) would be exceeded. Current: {current_position_size}, Order: {order_quantity}"
                + Style.RESET_ALL,
            )
        elif (
            ask_price > 0 and order_quantity >= self.min_order_quantity
        ):  # Ensure valid price and quantity
            # Upgrade 5: Wet-run flag
            if not self.simulate:
                signals.append(
                    (
                        "SELL_LIMIT",
                        ask_price,
                        timestamp,
                        {
                            "order_type": "LIMIT",
                            "quantity": order_quantity,
                            "strategy_id": "MM_ASK",
                            "created_at": datetime.utcnow(),
                        },
                    ),
                )  # Upgrade 1: Add timestamp
                self.logger.info(
                    Fore.GREEN
                    + f"Generated SELL LIMIT signal @ {ask_price:.8f}, Qty: {order_quantity:.4f}"
                    + Style.RESET_ALL,
                )
                signals_generated_this_cycle += 1
                if signals_generated_this_cycle >= self.max_signals_per_cycle:
                    return signals  # Upgrade 6: Cap signals
            else:
                self.logger.debug(
                    Fore.BLUE
                    + f"Simulated SELL LIMIT signal @ {ask_price:.8f}, Qty: {order_quantity:.4f}"
                    + Style.RESET_ALL,
                )

        # Upgrade 8: Emit summary signal
        signals.append(
            (
                "SUMMARY",
                None,
                timestamp,
                {
                    "total_signals": signals_generated_this_cycle,
                    "total_quantity_bid": sum(
                        s[3]["quantity"] for s in signals if s[0] == "BUY_LIMIT"
                    ),
                    "total_quantity_ask": sum(
                        s[3]["quantity"] for s in signals if s[0] == "SELL_LIMIT"
                    ),
                    "total_quantity_hedge": sum(
                        s[3]["quantity"]
                        for s in signals
                        if "HEDGE" in s[3]["strategy_id"]
                    ),
                    "average_bid_price": sum(
                        s[1] for s in signals if s[0] == "BUY_LIMIT"
                    )
                    / len([s for s in signals if s[0] == "BUY_LIMIT"])
                    if len([s for s in signals if s[0] == "BUY_LIMIT"]) > 0
                    else Decimal("0"),
                    "average_ask_price": sum(
                        s[1] for s in signals if s[0] == "SELL_LIMIT"
                    )
                    / len([s for s in signals if s[0] == "SELL_LIMIT"])
                    if len([s for s in signals if s[0] == "SELL_LIMIT"]) > 0
                    else Decimal("0"),
                    "created_at": datetime.utcnow(),
                },
            ),
        )

        return signals

    def generate_exit_signals(
        self,
        df: pd.DataFrame,
        current_position_side: str,
        active_bull_obs: list[
            OrderBlock
        ],  # Not used in exit, but kept for compatibility
        active_bear_obs: list[
            OrderBlock
        ],  # Not used in exit, but kept for compatibility
        **kwargs,
    ) -> list[tuple[str, Decimal, Any, dict[str, Any]]]:
        """Generate exit signals with dynamic stop-loss and rebalancing."""
        exit_signals = []
        signals_generated_this_cycle = 0

        if df.empty or current_position_side == "NONE":
            self.logger.warning(
                Fore.RED
                + "No position or empty DataFrame. Skipping exit signals."
                + Style.RESET_ALL,
            )
            return []

        latest_candle = df.iloc[-1]
        current_price_val = latest_candle["close"]
        latest_atr_val = latest_candle["atr"]

        if pd.isna(current_price_val) or pd.isna(latest_atr_val):
            self.logger.warning(
                Fore.RED
                + "Critical indicator values (close, atr) are NaN for exit signals. Cannot generate exit signals."
                + Style.RESET_ALL,
            )
            return []

        current_price = Decimal(str(current_price_val))
        latest_atr = Decimal(str(latest_atr_val))
        timestamp = df.index[-1]
        current_position_size = Decimal(str(kwargs.get("current_position_size", "0")))
        entry_price = Decimal(str(kwargs.get("entry_price", "0")))
        pnl = Decimal(str(kwargs.get("pnl", "0")))

        # Upgrade 9: Add defense against stale data
        now_utc = datetime.utcnow().replace(tzinfo=None)
        if now_utc - timestamp.to_pydatetime().replace(tzinfo=None) > timedelta(
            seconds=self.max_data_age_s,
        ):
            self.logger.warning(
                Fore.YELLOW + "Data is stale. Skipping exit cycle." + Style.RESET_ALL,
            )
            return []

        # --- Dynamic Stop-Loss ---
        if (
            self.use_dynamic_stop_loss and entry_price > 0 and current_position_size > 0
        ):  # Only apply if actually in a position
            stop_loss_trigger_price = Decimal("0")
            if current_position_side == "LONG":
                stop_loss_trigger_price = entry_price - (
                    latest_atr * self.stop_loss_atr_multiplier
                )
                if current_price <= stop_loss_trigger_price:
                    self.logger.warning(
                        Fore.RED
                        + f"PANIC EXIT (Long): Stop-Loss triggered at {current_price:.8f} (Entry: {entry_price:.8f}, SL: {stop_loss_trigger_price:.8f})"
                        + Style.RESET_ALL,
                    )
                    # Upgrade 5: Wet-run flag
                    if not self.simulate:
                        exit_signals.append(
                            (
                                "SELL_MARKET",
                                current_price,
                                timestamp,
                                {
                                    "order_type": "MARKET",
                                    "quantity": current_position_size,
                                    "strategy_id": "MM_PANIC_EXIT",
                                    "created_at": datetime.utcnow(),
                                },
                            ),
                        )  # Upgrade 1: Add timestamp
                        # Upgrade 3: Auto-tune stop_loss_atr_multiplier
                        if pnl < 0:
                            self.loss_count += 1
                        else:
                            self.win_count += 1
                        self.stop_loss_atr_multiplier *= Decimal("1") + (
                            Decimal(str(self.loss_count)) - Decimal(str(self.win_count))
                        ) / max(
                            Decimal("1"),
                            Decimal(str(self.win_count))
                            + Decimal(str(self.loss_count)),
                        )
                        self.logger.info(
                            Fore.MAGENTA
                            + f"Adjusted stop_loss_atr_multiplier to {self.stop_loss_atr_multiplier:.4f} (Wins: {self.win_count}, Losses: {self.loss_count})"
                            + Style.RESET_ALL,
                        )

                        signals_generated_this_cycle += 1
                        if signals_generated_this_cycle >= self.max_signals_per_cycle:
                            return exit_signals  # Upgrade 6: Cap signals
                    else:
                        self.logger.debug(
                            Fore.BLUE
                            + f"Simulated PANIC EXIT (Long): Stop-Loss triggered at {current_price:.8f}"
                            + Style.RESET_ALL,
                        )
                    return exit_signals  # Prioritize panic exit to avoid further losses
            elif current_position_side == "SHORT":
                stop_loss_trigger_price = entry_price + (
                    latest_atr * self.stop_loss_atr_multiplier
                )
                if current_price >= stop_loss_trigger_price:
                    self.logger.warning(
                        Fore.RED
                        + f"PANIC EXIT (Short): Stop-Loss triggered at {current_price:.8f} (Entry: {entry_price:.8f}, SL: {stop_loss_trigger_price:.8f})"
                        + Style.RESET_ALL,
                    )
                    # Upgrade 5: Wet-run flag
                    if not self.simulate:
                        exit_signals.append(
                            (
                                "BUY_MARKET",
                                current_price,
                                timestamp,
                                {
                                    "order_type": "MARKET",
                                    "quantity": current_position_size,
                                    "strategy_id": "MM_PANIC_EXIT",
                                    "created_at": datetime.utcnow(),
                                },
                            ),
                        )  # Upgrade 1: Add timestamp
                        # Upgrade 3: Auto-tune stop_loss_atr_multiplier
                        if pnl < 0:
                            self.loss_count += 1
                        else:
                            self.win_count += 1
                        self.stop_loss_atr_multiplier *= Decimal("1") + (
                            Decimal(str(self.loss_count)) - Decimal(str(self.win_count))
                        ) / max(
                            Decimal("1"),
                            Decimal(str(self.win_count))
                            + Decimal(str(self.loss_count)),
                        )
                        self.logger.info(
                            Fore.MAGENTA
                            + f"Adjusted stop_loss_atr_multiplier to {self.stop_loss_atr_multiplier:.4f} (Wins: {self.win_count}, Losses: {self.loss_count})"
                            + Style.RESET_ALL,
                        )

                        signals_generated_this_cycle += 1
                        if signals_generated_this_cycle >= self.max_signals_per_cycle:
                            return exit_signals  # Upgrade 6: Cap signals
                    else:
                        self.logger.debug(
                            Fore.BLUE
                            + f"Simulated PANIC EXIT (Short): Stop-Loss triggered at {current_price:.8f}"
                            + Style.RESET_ALL,
                        )
                    return exit_signals  # Prioritize panic exit

        # --- Rebalancing Logic ---
        # Rebalance only if position size is significant and not already being exited by SL
        if (
            current_position_size > self.rebalance_threshold
        ):  # Use > to trigger slightly above threshold
            self.logger.info(
                Fore.YELLOW
                + f"Rebalancing: Position size ({current_position_size}) >= threshold ({self.rebalance_threshold})."
                + Style.RESET_ALL,
            )
            exit_side = "SELL" if current_position_side == "LONG" else "BUY"

            # Upgrade 4: Partial rebalances
            rebalance_quantity = (
                current_position_size * self.rebalance_fraction
            )  # Close entire position for rebalance
            if rebalance_quantity < self.min_order_quantity:
                self.logger.warning(
                    Fore.YELLOW
                    + f"Rebalance quantity {rebalance_quantity:.4f} is too small to execute. Skipping."
                    + Style.RESET_ALL,
                )
                return []

            if self.rebalance_aggressiveness == "MARKET":
                # Upgrade 5: Wet-run flag
                if not self.simulate:
                    exit_signals.append(
                        (
                            f"{exit_side}_MARKET",
                            current_price,
                            timestamp,
                            {
                                "order_type": "MARKET",
                                "quantity": rebalance_quantity,
                                "strategy_id": "MM_REBALANCE",
                                "created_at": datetime.utcnow(),
                            },
                        ),
                    )  # Upgrade 1: Add timestamp
                    self.logger.info(
                        Fore.YELLOW
                        + f"Generated MARKET REBALANCE signal: Side={exit_side}, Qty={rebalance_quantity:.4f}"
                        + Style.RESET_ALL,
                    )
                    signals_generated_this_cycle += 1
                    if signals_generated_this_cycle >= self.max_signals_per_cycle:
                        return exit_signals  # Upgrade 6: Cap signals
                else:
                    self.logger.debug(
                        Fore.BLUE
                        + f"Simulated MARKET REBALANCE signal: Side={exit_side}, Qty={rebalance_quantity:.4f}"
                        + Style.RESET_ALL,
                    )

            else:  # AGGRESSIVE_LIMIT
                # Place limit order slightly inside the spread to get filled quickly
                aggressive_price = current_price
                # Calculate an aggressive limit price: current price adjusted by a small fraction of the spread
                aggressive_limit_adjustment = self._bps_to_pct(
                    self.spread_bps / Decimal("4"),
                )  # Half of the half spread
                if (
                    exit_side == "SELL"
                ):  # To sell aggressively, aim slightly below current price
                    aggressive_price = current_price * (
                        Decimal("1") - aggressive_limit_adjustment
                    )
                else:  # To buy aggressively, aim slightly above current price
                    aggressive_price = current_price * (
                        Decimal("1") + aggressive_limit_adjustment
                    )

                # Upgrade 5: Wet-run flag
                if not self.simulate:
                    exit_signals.append(
                        (
                            f"{exit_side}_LIMIT",
                            aggressive_price,
                            timestamp,
                            {
                                "order_type": "LIMIT",
                                "quantity": rebalance_quantity,
                                "strategy_id": "MM_REBALANCE",
                                "created_at": datetime.utcnow(),
                            },
                        ),
                    )  # Upgrade 1: Add timestamp
                    self.logger.info(
                        Fore.YELLOW
                        + f"Generated AGGRESSIVE LIMIT REBALANCE signal: Side={exit_side}, Price={aggressive_price:.8f}, Qty={rebalance_quantity:.4f}"
                        + Style.RESET_ALL,
                    )
                    signals_generated_this_cycle += 1
                    if signals_generated_this_cycle >= self.max_signals_per_cycle:
                        return exit_signals  # Upgrade 6: Cap signals
                else:
                    self.logger.debug(
                        Fore.BLUE
                        + f"Simulated AGGRESSIVE LIMIT REBALANCE signal: Side={exit_side}, Price={aggressive_price:.8f}, Qty={rebalance_quantity:.4f}"
                        + Style.RESET_ALL,
                    )

        # Upgrade 8: Emit summary signal
        exit_signals.append(
            (
                "SUMMARY",
                None,
                timestamp,
                {
                    "total_signals": signals_generated_this_cycle,
                    "total_quantity_exit": sum(
                        s[3]["quantity"] for s in exit_signals if s[0] != "SUMMARY"
                    ),
                    "average_exit_price": sum(
                        s[1] * s[3]["quantity"]
                        for s in exit_signals
                        if s[0] != "SUMMARY"
                    )
                    / sum(s[3]["quantity"] for s in exit_signals if s[0] != "SUMMARY")
                    if sum(s[3]["quantity"] for s in exit_signals if s[0] != "SUMMARY")
                    > 0
                    else Decimal("0"),
                    "created_at": datetime.utcnow(),
                },
            ),
        )

        self.logger.info(
            Fore.GREEN
            + f"Generated {len(exit_signals)} exit signals: {exit_signals}"
            + Style.RESET_ALL,
        )
        return exit_signals
