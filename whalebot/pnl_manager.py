# pnl_manager.py

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from precision_manager import PrecisionManager
from pybit.unified_trading import HTTP
from trade_metrics import TradeMetricsTracker


class PnLManager:
    """Manages comprehensive PnL tracking, account balance, and position details."""

    def __init__(
        self,
        http_session: HTTP,
        precision_manager: PrecisionManager,
        metrics_tracker: TradeMetricsTracker,
        logger: logging.Logger,
        initial_balance_usd: float = 0.0,  # From config
    ):
        self.http_session = http_session
        self.precision = precision_manager
        self.metrics = metrics_tracker
        self.logger = logger

        self.initial_balance_usd: Decimal = Decimal(str(initial_balance_usd))
        self.current_balance_usd: Decimal = Decimal("0")
        self.available_balance_usd: Decimal = Decimal("0")

        self.total_realized_pnl_usd: Decimal = Decimal(
            "0",
        )  # Updated from TradeMetricsTracker
        self.total_unrealized_pnl_usd: Decimal = Decimal("0")
        self.total_fees_paid_usd: Decimal = Decimal(
            "0",
        )  # Sum of fees from execution stream

        self.current_positions: dict[str, dict] = {}  # {symbol: {position_data}}
        self._lock = asyncio.Lock()  # For async updates

    async def initialize_balance(
        self,
        category: str = "linear",
        retry_delay: float = 5.0,
        max_retries: int = 3,
    ) -> float:
        """Initializes account balance and sets initial_balance_usd."""
        async with self._lock:
            account_type = (
                "UNIFIED" if category != "spot" else "SPOT"
            )  # Adjust accountType for API call
            for attempt in range(max_retries):
                try:
                    response = self.http_session.get_wallet_balance(
                        accountType=account_type,
                    )

                    if response["retCode"] == 0:
                        coins = response["result"]["list"][0][
                            "coin"
                        ]  # Assuming first account in list
                        for coin in coins:
                            if (
                                coin["coin"] == "USDT"
                            ):  # Assuming USDT as base quote currency
                                self.current_balance_usd = Decimal(
                                    coin["walletBalance"],
                                )
                                self.available_balance_usd = Decimal(
                                    coin.get(
                                        "availableToWithdraw",
                                        coin["walletBalance"],
                                    ),
                                )  # Use availableToWithdraw if present

                                if self.initial_balance_usd == Decimal(
                                    "0",
                                ):  # Set initial balance only once
                                    self.initial_balance_usd = self.current_balance_usd
                                self.logger.info(
                                    f"Balance initialized: Current={self.current_balance_usd:.2f} USDT, Available={self.available_balance_usd:.2f} USDT",
                                )
                                return float(self.current_balance_usd)
                        self.logger.warning(
                            f"USDT balance not found in wallet balance response for {account_type}. Attempt {attempt + 1}/{max_retries}.",
                        )
                        await asyncio.sleep(retry_delay)  # USDT not found, retry
                    else:
                        self.logger.error(
                            f"Failed to get wallet balance (attempt {attempt + 1}/{max_retries}): {response['retMsg']}. Retrying...",
                        )
                        await asyncio.sleep(retry_delay)
                except Exception as e:
                    self.logger.error(
                        f"Exception initializing balance (attempt {attempt + 1}/{max_retries}): {e}. Retrying...",
                    )
                    await asyncio.sleep(retry_delay)
            self.logger.critical(
                "Failed to initialize balance after multiple retries. Bot might not function correctly.",
            )
            return 0.0

    async def update_account_state_from_ws(self, ws_message: dict[str, Any]):
        """Updates account state (balance, positions, fees) from WebSocket private stream messages.
        This is typically called by the bot's private WS message handler.
        """
        async with self._lock:
            topic = ws_message.get("topic")
            data_list = ws_message.get("data", [])

            if topic == "wallet":
                for entry in data_list:
                    # Determine accountType for comparison, assume `linear` category if specs not available
                    category = self.precision.get_specs(entry.get("coin", ""))
                    account_type_for_check = (
                        "UNIFIED"
                        if category and category.category != "spot"
                        else "SPOT"
                    )

                    if (
                        entry.get("coin") == "USDT"
                        and entry.get("accountType") == account_type_for_check
                    ):
                        self.current_balance_usd = Decimal(entry["walletBalance"])
                        self.available_balance_usd = Decimal(
                            entry.get("availableToWithdraw", entry["walletBalance"]),
                        )
                        self.logger.debug(
                            f"WS Wallet update: {self.current_balance_usd:.2f} USDT (Available: {self.available_balance_usd:.2f})",
                        )
                        break
            elif topic == "position":
                for pos_entry in data_list:
                    symbol = pos_entry.get("symbol")
                    if symbol:
                        size = Decimal(pos_entry.get("size", "0"))
                        if size != Decimal("0"):  # Position is open
                            self.current_positions[symbol] = {
                                "size": size,
                                "side": pos_entry["side"],
                                "avg_price": Decimal(pos_entry["avgPrice"]),
                                "mark_price": Decimal(pos_entry["markPrice"]),
                                "unrealized_pnl": Decimal(pos_entry["unrealisedPnl"]),
                                "realized_pnl_cum": Decimal(
                                    pos_entry.get("cumRealisedPnl", "0"),
                                ),  # Cumulative realized
                                "value_usd": size
                                * Decimal(pos_entry["markPrice"])
                                * self.precision.get_specs(
                                    symbol,
                                ).contract_value,  # Notional value for inverse
                                "margin_usd": Decimal(pos_entry["positionIM"]),
                                "leverage": Decimal(pos_entry["leverage"]),
                                "liq_price": Decimal(pos_entry["liqPrice"]),
                                "updated_at": datetime.now(),
                            }
                        elif symbol in self.current_positions:  # Position is closed
                            self.logger.info(f"WS Position closed for {symbol}.")
                            del self.current_positions[symbol]

            elif topic == "execution":
                # Track fees from executions
                for exec_entry in data_list:
                    exec_fee = Decimal(exec_entry.get("execFee", "0"))
                    if exec_fee > Decimal("0"):
                        self.total_fees_paid_usd += exec_fee
                        self.logger.debug(
                            f"WS Execution fee: {exec_fee:.6f} for {exec_entry.get('orderId')}. Total fees: {self.total_fees_paid_usd:.6f}",
                        )

    async def update_all_positions_pnl(self, current_prices: dict[str, float]):
        """Updates unrealized PnL for all tracked positions and calculates total.
        This also updates max_profit/loss for individual trades in TradeMetricsTracker.
        """
        async with self._lock:
            self.total_unrealized_pnl_usd = self.metrics.update_unrealized_pnl(
                current_prices,
            )
            self.logger.debug(
                f"Total Unrealized PnL: {self.total_unrealized_pnl_usd:.2f} USDT",
            )

    async def get_total_account_pnl_summary(self) -> dict:
        """Calculates and returns a comprehensive PnL summary for the entire account."""
        async with self._lock:
            self.total_realized_pnl_usd = self.metrics.calculate_metrics()[
                "total_pnl_usd"
            ]

            # The current_balance_usd already reflects realized PnL.
            # So, total_return = current_balance - initial_balance.
            # Adding total_realized_pnl_usd again would be double counting.
            overall_return_usd = self.current_balance_usd - self.initial_balance_usd

            if self.initial_balance_usd == Decimal("0"):
                return_percentage = Decimal("0")
            else:
                return_percentage = (
                    overall_return_usd / self.initial_balance_usd * 100
                ).quantize(Decimal("0.01"))

            return {
                "initial_balance_usd": float(self.initial_balance_usd),
                "current_wallet_balance_usd": float(self.current_balance_usd),
                "available_balance_usd": float(self.available_balance_usd),
                "total_realized_pnl_usd": float(self.total_realized_pnl_usd),
                "total_unrealized_pnl_usd": float(self.total_unrealized_pnl_usd),
                "overall_total_pnl_usd": float(
                    self.total_realized_pnl_usd + self.total_unrealized_pnl_usd,
                ),
                "overall_return_usd": float(
                    overall_return_usd,
                ),  # This is current_wallet_balance - initial_balance
                "overall_return_percentage": float(return_percentage),
                "total_fees_paid_usd": float(self.total_fees_paid_usd),
                "num_open_positions": len(self.current_positions),
                "total_position_value_usd": float(
                    sum(p["value_usd"] for p in self.current_positions.values()),
                ),
                "total_margin_in_use_usd": float(
                    sum(p["margin_usd"] for p in self.current_positions.values()),
                ),
            }

    async def get_position_summary(
        self,
        symbol: str | None = None,
    ) -> list[dict] | dict | None:
        """Gets a summary of all or a specific open position(s)."""
        async with self._lock:
            if symbol:
                if symbol in self.current_positions:
                    pos = self.current_positions[symbol]
                    # Calculate PnL percentage based on margin
                    pnl_percentage = (
                        (pos["unrealized_pnl"] / pos["margin_usd"] * 100)
                        if pos["margin_usd"] > Decimal("0")
                        else Decimal("0")
                    )
                    # Calculate Distance to Liquidation (if applicable)
                    distance_to_liq_pct = Decimal("0")
                    if pos["liq_price"] > Decimal("0") and pos["mark_price"] > Decimal(
                        "0",
                    ):
                        distance_to_liq_pct = (
                            abs(pos["mark_price"] - pos["liq_price"])
                            / pos["mark_price"]
                            * 100
                        )

                    return {
                        "symbol": symbol,
                        "side": pos["side"],
                        "size": float(pos["size"]),
                        "avg_price": float(pos["avg_price"]),
                        "mark_price": float(pos["mark_price"]),
                        "value_usd": float(pos["value_usd"]),
                        "unrealized_pnl_usd": float(pos["unrealized_pnl"]),
                        "realized_pnl_cum_usd": float(pos["realized_pnl_cum"]),
                        "pnl_percentage_on_margin": float(pnl_percentage),
                        "leverage": float(pos["leverage"]),
                        "margin_usd": float(pos["margin_usd"]),
                        "liq_price": float(pos["liq_price"]),
                        "distance_to_liq_pct": float(distance_to_liq_pct),
                        "updated_at": pos["updated_at"].isoformat(),
                    }
                return None  # Specific symbol not found
            # Return all positions
            summaries = []
            for s, p in self.current_positions.items():
                pnl_percentage = (
                    (p["unrealized_pnl"] / p["margin_usd"] * 100)
                    if p["margin_usd"] > Decimal("0")
                    else Decimal("0")
                )
                distance_to_liq_pct = Decimal("0")
                if p["liq_price"] > Decimal("0") and p["mark_price"] > Decimal("0"):
                    distance_to_liq_pct = (
                        abs(p["mark_price"] - p["liq_price"]) / p["mark_price"] * 100
                    )

                summaries.append(
                    {
                        "symbol": s,
                        "side": p["side"],
                        "size": float(p["size"]),
                        "avg_price": float(p["avg_price"]),
                        "mark_price": float(p["mark_price"]),
                        "value_usd": float(p["value_usd"]),
                        "unrealized_pnl_usd": float(p["unrealized_pnl"]),
                        "pnl_percentage_on_margin": float(pnl_percentage),
                        "leverage": float(p["leverage"]),
                        "margin_usd": float(p["margin_usd"]),
                        "liq_price": float(p["liq_price"]),
                        "distance_to_liq_pct": float(distance_to_liq_pct),
                        "updated_at": p["updated_at"].isoformat(),
                    },
                )
            return summaries
            return None  # No position found
