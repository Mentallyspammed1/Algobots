import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from colorama import Fore, Style

# Import local modules
from whalebot_pro.api.bybit_client import BybitClient
from whalebot_pro.core.performance_tracker import PerformanceTracker

# Color Scheme
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
RESET = Style.RESET_ALL

TIMEZONE = UTC  # Default, will be overwritten by config


class PositionManager:
    """Manages open positions, stop-loss, and take-profit levels."""

    def __init__(
        self, config: dict[str, Any], logger: logging.Logger, bybit_client: BybitClient
    ):
        """Initializes the PositionManager."""
        self.config = config
        self.logger = logger
        self.bybit_client = bybit_client
        self.symbol = config["symbol"]
        self.open_positions: list[dict] = []
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]

        # Precision Manager is now part of BybitClient
        self.precision_manager = self.bybit_client.precision_manager

        self.enable_trailing_stop = config["trade_management"].get(
            "enable_trailing_stop", False
        )
        self.trailing_stop_atr_multiple = Decimal(
            str(config["trade_management"].get("trailing_stop_atr_multiple", 0.0))
        )
        self.break_even_atr_trigger = Decimal(
            str(config["trade_management"].get("break_even_atr_trigger", 0.0))
        )

        self.move_to_breakeven_atr_trigger = Decimal(
            str(config["trade_management"].get("move_to_breakeven_atr_trigger", 0.0))
        )
        self.profit_lock_in_atr_multiple = Decimal(
            str(config["trade_management"].get("profit_lock_in_atr_multiple", 0.0))
        )
        self.close_on_opposite_signal = config["trade_management"].get(
            "close_on_opposite_signal", True
        )
        self.reverse_position_on_opposite_signal = config["trade_management"].get(
            "reverse_position_on_opposite_signal", False
        )

        # Initial sync of open positions from exchange
        # This will be called in the main loop after client initialization

    async def _get_current_balance(self) -> Decimal:
        """Fetch current account balance from exchange."""
        balance = await self.bybit_client.get_wallet_balance()
        if balance is None:
            self.logger.warning(
                f"{NEON_YELLOW}Could not fetch real account balance. Using configured balance for simulation.{RESET}"
            )
            return Decimal(str(self.config["trade_management"]["account_balance"]))
        return balance

    async def _calculate_order_size(
        self, current_price: Decimal, atr_value: Decimal
    ) -> Decimal:
        """Calculate order size based on risk per trade and ATR."""
        if not self.trade_management_enabled:
            return Decimal("0")

        account_balance = await self._get_current_balance()
        risk_per_trade_percent = (
            Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
            / 100
        )
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"])
        )

        risk_amount = account_balance * risk_per_trade_percent
        stop_loss_distance = atr_value * stop_loss_atr_multiple

        if stop_loss_distance <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated stop loss distance is zero or negative ({stop_loss_distance}). Cannot determine order size.{RESET}"
            )
            return Decimal("0")

        order_value = risk_amount / stop_loss_distance
        order_qty = order_value / current_price

        # Use precision manager to round quantity
        order_qty = self.precision_manager.round_qty(order_qty, self.symbol)

        min_qty = self.precision_manager.get_min_qty(self.symbol)
        if order_qty < min_qty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated order quantity {order_qty} is less than min_qty {min_qty}. Adjusting to min_qty.{RESET}"
            )
            order_qty = min_qty

        self.logger.info(
            f"[{self.symbol}] Calculated order size: {order_qty.normalize()} (Risk: {risk_amount.normalize():.2f} USD)"
        )
        return order_qty

    async def sync_positions_from_exchange(self):
        """Fetches current open positions from the exchange and updates the internal list."""
        exchange_positions = await self.bybit_client.get_positions()

        new_open_positions = []
        for ex_pos in exchange_positions:
            side = ex_pos["side"]
            qty = Decimal(ex_pos["size"])
            entry_price = Decimal(ex_pos["avgPrice"])
            stop_loss_price = (
                Decimal(ex_pos.get("stopLoss", "0"))
                if ex_pos.get("stopLoss")
                else Decimal("0")
            )
            take_profit_price = (
                Decimal(ex_pos.get("takeProfit", "0"))
                if ex_pos.get("takeProfit")
                else Decimal("0")
            )
            trailing_stop = (
                Decimal(ex_pos.get("trailingStop", "0"))
                if ex_pos.get("trailingStop")
                else Decimal("0")
            )

            position_id = str(ex_pos.get("positionId", ex_pos.get("positionIdx", 0)))
            position_idx_int = int(ex_pos.get("positionIdx", 0))

            existing_pos = next(
                (
                    p
                    for p in self.open_positions
                    if p.get("position_id") == position_id and p.get("side") == side
                ),
                None,
            )

            if existing_pos:
                existing_pos.update(
                    {
                        "entry_price": self.precision_manager.round_price(
                            entry_price, self.symbol
                        ),
                        "qty": self.precision_manager.round_qty(qty, self.symbol),
                        "stop_loss": self.precision_manager.round_price(
                            stop_loss_price, self.symbol
                        ),
                        "take_profit": self.precision_manager.round_price(
                            take_profit_price, self.symbol
                        ),
                        "trailing_stop_price": self.precision_manager.round_price(
                            trailing_stop, self.symbol
                        )
                        if trailing_stop
                        else None,
                        "trailing_stop_activated": trailing_stop > 0
                        if self.enable_trailing_stop
                        else False,
                        "breakeven_activated": existing_pos.get(
                            "breakeven_activated", False
                        ),
                    }
                )
                new_open_positions.append(existing_pos)
            else:
                self.logger.warning(
                    f"{NEON_YELLOW}[{self.symbol}] Detected new untracked position on exchange. Side: {side}, Qty: {qty}, Entry: {entry_price}. Adding to internal tracking.{RESET}"
                )
                new_open_positions.append(
                    {
                        "positionIdx": position_idx_int,
                        "side": side,
                        "entry_price": self.precision_manager.round_price(
                            entry_price, self.symbol
                        ),
                        "qty": self.precision_manager.round_qty(qty, self.symbol),
                        "stop_loss": self.precision_manager.round_price(
                            stop_loss_price, self.symbol
                        ),
                        "take_profit": self.precision_manager.round_price(
                            take_profit_price, self.symbol
                        ),
                        "position_id": position_id,
                        "order_id": "UNKNOWN",
                        "entry_time": datetime.now(self.bybit_client.timezone),
                        "initial_stop_loss": self.precision_manager.round_price(
                            stop_loss_price, self.symbol
                        ),
                        "trailing_stop_activated": trailing_stop > 0
                        if self.enable_trailing_stop
                        else False,
                        "trailing_stop_price": self.precision_manager.round_price(
                            trailing_stop, self.symbol
                        )
                        if trailing_stop
                        else None,
                        "breakeven_activated": False,
                    }
                )

        for tracked_pos in self.open_positions:
            is_still_open = any(
                str(ex_pos.get("positionId", ex_pos.get("positionIdx")))
                == tracked_pos.get("position_id")
                and ex_pos["side"] == tracked_pos["side"]
                for ex_pos in exchange_positions
            )
            if not is_still_open:
                self.logger.info(
                    f"{NEON_BLUE}[{self.symbol}] Position {tracked_pos['side']} (ID: {tracked_pos.get('position_id', 'N/A')}) no longer open on exchange. Marking as closed.{RESET}"
                )

        self.open_positions = new_open_positions
        if not self.open_positions:
            self.logger.debug(
                f"[{self.symbol}] No active positions being tracked internally."
            )

    async def open_position(
        self,
        signal_side: Literal["Buy", "Sell"],
        current_price: Decimal,
        atr_value: Decimal,
    ) -> dict | None:
        """Open a new position if conditions allow, interacting with the Bybit API."""
        if not self.trade_management_enabled:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Trade management is disabled. Skipping opening position.{RESET}"
            )
            return None

        await self.sync_positions_from_exchange()
        if len(self.get_open_positions()) >= self.max_open_positions:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}"
            )
            return None

        if any(
            p["side"].upper() == signal_side.upper() for p in self.get_open_positions()
        ):
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Already have an open {signal_side} position. Skipping new entry.{RESET}"
            )
            return None

        order_qty = await self._calculate_order_size(current_price, atr_value)
        if order_qty <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Order quantity is zero or negative ({order_qty}). Cannot open position.{RESET}"
            )
            return None

        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"])
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"])
        )

        if signal_side == "Buy":
            initial_stop_loss = current_price - (atr_value * stop_loss_atr_multiple)
            take_profit = current_price + (atr_value * take_profit_atr_multiple)
        else:  # Sell
            initial_stop_loss = current_price + (atr_value * stop_loss_atr_multiple)
            take_profit = current_price - (atr_value * take_profit_atr_multiple)

        # Round SL/TP using precision manager
        initial_stop_loss = self.precision_manager.round_price(
            initial_stop_loss, self.symbol
        )
        take_profit = self.precision_manager.round_price(take_profit, self.symbol)

        order_result = await self.bybit_client.place_order(
            side=signal_side,
            qty=order_qty,
            order_type="Market",
            stop_loss=initial_stop_loss,
            take_profit=take_profit,
        )

        if not order_result:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Failed to place market order for {signal_side} {order_qty.normalize()}.{RESET}"
            )
            return None

        filled_qty = Decimal(order_result.get("qty", str(order_qty)))
        filled_price = Decimal(order_result.get("avgPrice", str(current_price)))
        order_id = order_result.get("orderId")
        position_idx_on_exchange = int(order_result.get("positionIdx", 0))

        new_position = {
            "positionIdx": position_idx_on_exchange,
            "symbol": self.symbol,
            "side": signal_side,
            "entry_price": self.precision_manager.round_price(
                filled_price, self.symbol
            ),
            "qty": self.precision_manager.round_qty(filled_qty, self.symbol),
            "stop_loss": initial_stop_loss,
            "take_profit": take_profit,
            "position_id": str(position_idx_on_exchange),
            "order_id": order_id,
            "entry_time": datetime.now(self.bybit_client.timezone),
            "initial_stop_loss": initial_stop_loss,
            "trailing_stop_activated": False,
            "trailing_stop_price": None,
            "breakeven_activated": False,
        }
        self.open_positions.append(new_position)
        self.logger.info(
            f"{NEON_GREEN}[{self.symbol}] Successfully opened {signal_side} position and set initial TP/SL: {new_position}{RESET}"
        )
        return new_position

    async def close_position(
        self,
        position: dict,
        current_price: Decimal,
        performance_tracker: PerformanceTracker,
        closed_by: str = "SIGNAL",
    ) -> None:
        """Closes an existing position by placing a market order in the opposite direction."""
        if not self.trade_management_enabled:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Trade management is disabled. Cannot close position.{RESET}"
            )
            return

        side_to_close = "Sell" if position["side"] == "Buy" else "Buy"
        qty_to_close = position["qty"]

        self.logger.info(
            f"{NEON_BLUE}[{self.symbol}] Attempting to close {position['side']} position (ID: {position['position_id']}) with {side_to_close} order for {qty_to_close.normalize()}...{RESET}"
        )

        order_result = await self.bybit_client.place_order(
            side=side_to_close,
            qty=qty_to_close,
            order_type="Market",
            reduce_only=True,  # Ensure this closes the position
        )

        if order_result:
            self.logger.info(
                f"{NEON_GREEN}[{self.symbol}] Close order placed successfully: {order_result}{RESET}"
            )
            exit_price = Decimal(order_result.get("avgPrice", str(current_price)))

            pnl = (
                (exit_price - position["entry_price"]) * position["qty"]
                if position["side"] == "Buy"
                else (position["entry_price"] - exit_price) * position["qty"]
            )

            performance_tracker.record_trade(
                {
                    **position,
                    "exit_price": exit_price,
                    "exit_time": datetime.now(self.bybit_client.timezone),
                    "closed_by": closed_by,
                },
                pnl,
            )

            self.open_positions = [
                p
                for p in self.open_positions
                if p["position_id"] != position["position_id"]
                or p["side"] != position["side"]
            ]
            self.logger.info(
                f"{NEON_GREEN}[{self.symbol}] Position (ID: {position['position_id']}) removed from internal tracking.{RESET}"
            )
        else:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Failed to place close order for position (ID: {position['position_id']}). Manual intervention might be needed!{RESET}"
            )

    async def manage_positions(
        self,
        current_price: Decimal,
        performance_tracker: PerformanceTracker,
        atr_value: Decimal,
    ) -> None:
        """Syncs open positions from the exchange and applies dynamic stop loss logic.
        Records closed positions based on exchange updates.
        """
        if not self.trade_management_enabled:
            return

        await self.sync_positions_from_exchange()

        current_internal_positions = list(self.open_positions)
        positions_closed_on_exchange_ids = set()

        for position in current_internal_positions:
            latest_pos_from_sync = next(
                (
                    p
                    for p in self.open_positions
                    if p.get("position_id") == position.get("position_id")
                    and p.get("side") == position.get("side")
                ),
                None,
            )

            if not latest_pos_from_sync:
                close_price = current_price
                closed_by = "UNKNOWN"
                if position["side"] == "Buy":
                    if current_price <= position["stop_loss"]:
                        closed_by = "STOP_LOSS"
                    elif current_price >= position["take_profit"]:
                        closed_by = "TAKE_PROFIT"
                elif current_price >= position["stop_loss"]:
                    closed_by = "STOP_LOSS"
                elif current_price <= position["take_profit"]:
                    closed_by = "TAKE_PROFIT"

                pnl = (
                    (close_price - position["entry_price"]) * position["qty"]
                    if position["side"] == "Buy"
                    else (position["entry_price"] - close_price) * position["qty"]
                )

                performance_tracker.record_trade(
                    {
                        **position,
                        "exit_price": self.precision_manager.round_price(
                            close_price, self.symbol
                        ),
                        "exit_time": datetime.now(self.bybit_client.timezone),
                        "closed_by": closed_by,
                    },
                    pnl,
                )
                positions_closed_on_exchange_ids.add(position.get("position_id"))
                self.logger.info(
                    f"{NEON_BLUE}[{self.symbol}] Detected and recorded closure of {position['side']} position (ID: {position.get('position_id')}). PnL: {pnl.normalize():.2f}{RESET}"
                )
                continue

            position = latest_pos_from_sync

            side = position["side"]
            entry_price = position["entry_price"]
            current_stop_loss_on_exchange = position["stop_loss"]

            potential_sl_update = None
            if atr_value > 0:
                profit_since_entry_atr = (
                    current_price - entry_price
                ).copy_abs() / atr_value

                if (
                    self.move_to_breakeven_atr_trigger > 0
                    and not position.get("breakeven_activated", False)
                    and (
                        (
                            side == "Buy"
                            and current_price
                            >= (
                                entry_price
                                + atr_value * self.move_to_breakeven_atr_trigger
                            )
                        )
                        or (
                            side == "Sell"
                            and current_price
                            <= (
                                entry_price
                                - atr_value * self.move_to_breakeven_atr_trigger
                            )
                        )
                    )
                ):
                    breakeven_sl = entry_price
                    if side == "Buy":
                        potential_sl_update = max(
                            current_stop_loss_on_exchange, breakeven_sl
                        )
                    else:
                        potential_sl_update = min(
                            current_stop_loss_on_exchange, breakeven_sl
                        )

                    if potential_sl_update != current_stop_loss_on_exchange:
                        self.logger.info(
                            f"{NEON_BLUE}[{self.symbol}] Breakeven condition met for {side} position (ID: {position['position_id']}). Moving SL to {potential_sl_update.normalize()}.{RESET}"
                        )
                        position["breakeven_activated"] = True
                    else:
                        potential_sl_update = None

                if self.profit_lock_in_atr_multiple > 0:
                    profit_lock_sl_candidate = (
                        (current_price - (atr_value * self.profit_lock_in_atr_multiple))
                        if side == "Buy"
                        else (
                            current_price
                            + (atr_value * self.profit_lock_in_atr_multiple)
                        )
                    )

                    should_update_profit_lock = False
                    if (
                        side == "Buy"
                        and profit_lock_sl_candidate > current_stop_loss_on_exchange
                        and profit_lock_sl_candidate > entry_price
                    ) or (
                        side == "Sell"
                        and profit_lock_sl_candidate < current_stop_loss_on_exchange
                        and profit_lock_sl_candidate < entry_price
                    ):
                        should_update_profit_lock = True

                    if should_update_profit_lock:
                        if potential_sl_update:
                            if side == "Buy":
                                potential_sl_update = max(
                                    potential_sl_update, profit_lock_sl_candidate
                                )
                            else:
                                potential_sl_update = min(
                                    potential_sl_update, profit_lock_sl_candidate
                                )
                        else:
                            potential_sl_update = profit_lock_sl_candidate
                        self.logger.info(
                            f"{NEON_BLUE}[{self.symbol}] Profit lock-in condition met for {side} position (ID: {position['position_id']}). Moving SL to {potential_sl_update.normalize()}.{RESET}"
                        )

            if self.enable_trailing_stop and atr_value > 0:
                profit_trigger_level = (
                    entry_price + (atr_value * self.break_even_atr_trigger)
                    if side == "Buy"
                    else entry_price - (atr_value * self.break_even_atr_trigger)
                )

                if (side == "Buy" and current_price >= profit_trigger_level) or (
                    side == "Sell" and current_price <= profit_trigger_level
                ):
                    position["trailing_stop_activated"] = True

                    new_trailing_stop_candidate = (
                        (current_price - (atr_value * self.trailing_stop_atr_multiple))
                        if side == "Buy"
                        else (
                            current_price
                            + (atr_value * self.trailing_stop_atr_multiple)
                        )
                    )

                    should_update_tsl = False

                    if side == "Buy":
                        if new_trailing_stop_candidate > current_stop_loss_on_exchange:
                            proposed_sl = max(
                                new_trailing_stop_candidate,
                                position["initial_stop_loss"],
                            )
                            if potential_sl_update:
                                proposed_sl = max(proposed_sl, potential_sl_update)
                            if proposed_sl > current_stop_loss_on_exchange:
                                should_update_tsl = True
                                potential_sl_update = proposed_sl
                    elif side == "Sell":
                        if new_trailing_stop_candidate < current_stop_loss_on_exchange:
                            proposed_sl = min(
                                new_trailing_stop_candidate,
                                position["initial_stop_loss"],
                            )
                            if potential_sl_update:
                                proposed_sl = min(proposed_sl, potential_sl_update)
                            if proposed_sl < current_stop_loss_on_exchange:
                                should_update_tsl = True
                                potential_sl_update = proposed_sl

                    if (not should_update_tsl and potential_sl_update is None) or (
                        should_update_tsl and potential_sl_update is not None
                    ):
                        pass
                    elif should_update_tsl and potential_sl_update is None:
                        potential_sl_update = proposed_sl

            if (
                potential_sl_update is not None
                and potential_sl_update != current_stop_loss_on_exchange
            ):
                # Round the potential SL update using precision manager
                potential_sl_update = self.precision_manager.round_price(
                    potential_sl_update, self.symbol
                )

                tpsl_update_result = await self.bybit_client.set_trading_stop(
                    stop_loss=potential_sl_update,
                    take_profit=position["take_profit"],
                    position_idx=position["positionIdx"],
                )
                if tpsl_update_result:
                    position["stop_loss"] = potential_sl_update
                    position["trailing_stop_price"] = potential_sl_update
                    self.logger.info(
                        f"{NEON_GREEN}[{self.symbol}] Stop Loss Updated for {side} position (ID: {position['position_id']}): Entry: {entry_price.normalize()}, Current Price: {current_price.normalize()}, New SL: {potential_sl_update.normalize()}{RESET}"
                    )
                else:
                    self.logger.error(
                        f"{NEON_RED}[{self.symbol}] Failed to update SL for {side} position (ID: {position['position_id']}).{RESET}"
                    )

        self.open_positions = [
            pos
            for pos in self.open_positions
            if pos.get("position_id") not in positions_closed_on_exchange_ids
        ]

    def get_open_positions(self) -> list[dict]:
        """Return a list of currently open positions tracked internally."""
        return self.open_positions
