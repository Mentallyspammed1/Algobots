import asyncio
from decimal import Decimal
from typing import Any

import config
from bot_logger import log_exception
from bybit_api import BybitAPIError, BybitContractAPI
from utils import calculate_order_quantity

# --- Pyrmethus's Color Codex ---
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_DIM = "\033[2m"
COLOR_RED = "\033[31m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_BLUE = "\033[34m"
COLOR_MAGENTA = "\033[35m"
COLOR_CYAN = "\033[36m"
PYRMETHUS_GREEN = COLOR_GREEN
PYRMETHUS_BLUE = COLOR_BLUE
PYRMETHUS_PURPLE = COLOR_MAGENTA
PYRMETHUS_ORANGE = COLOR_YELLOW
PYRMETHUS_GREY = COLOR_DIM
PYRMETHUS_YELLOW = COLOR_YELLOW
PYRMETHUS_CYAN = COLOR_CYAN


class OrderManager:
    """Manages all aspects of order execution, including placing, amending, and exiting trades.
    This class abstracts the order logic away from the main bot loop.
    """

    def __init__(self, bybit_client: BybitContractAPI, bot_instance):
        self.bybit_client = bybit_client
        self.bot = bot_instance
        self.logger = bot_instance.bot_logger

    async def _get_instrument_info(self, symbol: str) -> dict[str, Decimal] | None:
        """Fetches and returns instrument details like min quantity and step size."""
        try:
            instrument_info_resp = await self.bybit_client.get_instruments_info(
                category=config.BYBIT_CATEGORY, symbol=symbol,
            )
            if (
                not instrument_info_resp
                or instrument_info_resp.get("retCode") != 0
                or not instrument_info_resp.get("result", {}).get("list")
            ):
                raise ValueError(
                    f"Failed to fetch instrument info: {instrument_info_resp.get('retMsg', 'N/A')}",
                )

            instrument = instrument_info_resp["result"]["list"][0]
            return {
                "min_qty": Decimal(
                    instrument.get("lotSizeFilter", {}).get("minOrderQty", "0.001"),
                ),
                "qty_step": Decimal(
                    instrument.get("lotSizeFilter", {}).get("qtyStep", "0.001"),
                ),
                "min_order_value": Decimal(
                    instrument.get("lotSizeFilter", {}).get("minOrderIv", "10"),
                ),
            }
        except BybitAPIError as e:
            await self.bot._handle_api_error(
                e, f"fetching instrument info for {symbol}",
            )
            return None
        except Exception as e:
            log_exception(
                self.logger,
                f"Error fetching or parsing instrument info for {symbol}: {e}",
                e,
            )
            return None

    async def _get_usdt_balance(self) -> Decimal:
        """Fetches and returns the available USDT wallet balance."""
        try:
            balance_response = await self.bybit_client.get_wallet_balance(
                accountType="UNIFIED", coin="USDT",
            )
            if (
                balance_response
                and balance_response.get("retCode") == 0
                and balance_response.get("result", {}).get("list")
            ):
                usdt_balance_data = next(
                    (
                        item
                        for item in balance_response["result"]["list"]
                        if item["coin"][0]["coin"] == "USDT"
                    ),
                    None,
                )
                if usdt_balance_data:
                    return Decimal(usdt_balance_data["coin"][0]["walletBalance"])
            self.logger.warning(
                f"{PYRMETHUS_YELLOW}Could not retrieve USDT balance. Response: {balance_response.get('retMsg', 'N/A')}{COLOR_RESET}",
            )
            return Decimal("0")
        except BybitAPIError as e:
            await self.bot._handle_api_error(e, "fetching USDT balance")
            return Decimal("0")
        except Exception as e:
            log_exception(self.logger, f"Error fetching USDT balance: {e}", e)
            return Decimal("0")

    async def _get_current_execution_price(self, symbol: str) -> Decimal:
        """Fetches the latest market price for immediate execution calculations."""
        try:
            ticker_info = await self.bybit_client.get_symbol_ticker(
                category=config.BYBIT_CATEGORY, symbol=symbol,
            )
            if (
                not ticker_info
                or ticker_info.get("retCode") != 0
                or not ticker_info.get("result", {}).get("list")
            ):
                raise ValueError(
                    f"Failed to fetch ticker info: {ticker_info.get('retMsg', 'N/A')}",
                )
            return Decimal(str(ticker_info["result"]["list"][0]["lastPrice"]))
        except BybitAPIError as e:
            await self.bot._handle_api_error(e, f"fetching current price for {symbol}")
            return Decimal("0")
        except Exception as e:
            log_exception(
                self.logger, f"Failed to fetch current price for {symbol}: {e}", e,
            )
            return Decimal("0")

    async def execute_entry(
        self,
        signal_type: str,
        signal_price: Decimal,
        signal_timestamp: Any,
        signal_info: dict[str, Any],
    ) -> bool:
        """Handles the complete logic for executing an entry order."""
        self.logger.info(
            f"{PYRMETHUS_PURPLE}💡 OrderManager received {signal_type.upper()} signal at {signal_price:.4f}{COLOR_RESET}",
        )

        # --- Pre-flight Checks ---
        usdt_balance = await self._get_usdt_balance()
        if (
            usdt_balance < config.USDT_AMOUNT_PER_TRADE
            and not config.USE_PERCENTAGE_ORDER_SIZING
        ):
            self.logger.warning(
                f"{PYRMETHUS_YELLOW}Insufficient balance ({usdt_balance:.2f}) for fixed trade amount. Skipping.{COLOR_RESET}",
            )
            return False

        instrument_info = await self._get_instrument_info(config.SYMBOL)
        if not instrument_info:
            return False

        current_price = await self._get_current_execution_price(config.SYMBOL)
        if current_price <= 0:
            self.logger.error(
                f"{COLOR_RED}Invalid execution price ({current_price}). Aborting order.{COLOR_RESET}",
            )
            return False

        # --- Calculate Order Size ---
        target_usdt_value = config.USDT_AMOUNT_PER_TRADE
        if config.USE_PERCENTAGE_ORDER_SIZING:
            volatility_factor = Decimal("1")
            if self.bot.cached_atr and current_price > 0:
                volatility_factor = min(
                    Decimal("1"), self.bot.cached_atr / current_price,
                )
            target_usdt_value = (
                usdt_balance
                * (config.ORDER_SIZE_PERCENT_OF_BALANCE / Decimal("100"))
                * volatility_factor
            )
            self.logger.info(
                f"{PYRMETHUS_BLUE}Dynamic sizing: Balance={usdt_balance:.2f}, Volatility Factor={volatility_factor:.3f}, Target USDT={target_usdt_value:.2f}{COLOR_RESET}",
            )

        quantity = calculate_order_quantity(
            usdt_amount=target_usdt_value,
            current_price=current_price,
            min_qty=instrument_info["min_qty"],
            qty_step=instrument_info["qty_step"],
            min_order_value=instrument_info["min_order_value"],
            logger=self.logger,
        )

        if quantity <= 0:
            self.logger.error(
                f"{COLOR_RED}Final calculated quantity is zero or negative. Aborting order.{COLOR_RESET}",
            )
            return False

        # --- Place Order ---
        side = "Buy" if "BUY" in signal_type else "Sell"
        order_kwargs = {
            "category": config.BYBIT_CATEGORY,
            "symbol": config.SYMBOL,
            "side": side,
            "order_type": "Limit",
            "qty": f"{quantity:.8f}",
            "price": f"{signal_price:.4f}",
        }
        if config.HEDGE_MODE:
            order_kwargs["positionIdx"] = 1 if side == "Buy" else 2
        else:
            order_kwargs["positionIdx"] = 0

        self.logger.info(
            f"{PYRMETHUS_ORANGE}Placing {signal_type.upper()} Limit order: Qty={quantity:.4f} @ {signal_price:.4f}{COLOR_RESET}",
        )

        try:
            response = await self.bybit_client.create_order(**order_kwargs)
            if response and response.get("retCode") == 0:
                order_id = response.get("result", {}).get("orderId")
                self.logger.info(
                    f"{PYRMETHUS_GREEN}Successfully placed order {order_id}.{COLOR_RESET}",
                )
                if order_id:
                    asyncio.create_task(
                        self.chase_limit_order(order_id, config.SYMBOL, side),
                    )
                return True
            self.logger.error(
                f"{COLOR_RED}Order placement failed. Response: {response.get('retMsg', 'Unknown error')}{COLOR_RESET}",
            )
            return False
        except BybitAPIError as e:
            await self.bot._handle_api_error(e, "order placement")
            return False
        except Exception as e:
            log_exception(self.logger, "Exception during order placement", e)
            return False

    async def execute_exit(
        self,
        inventory: Decimal,
        exit_type: str,
        exit_price: Decimal,
        exit_timestamp: Any,
        exit_info: dict[str, Any],
    ) -> bool:
        """Handles the complete logic for executing a market exit order."""
        self.logger.info(
            f"{PYRMETHUS_PURPLE}💡 OrderManager received {exit_type.upper()} exit signal at {exit_price:.4f}{COLOR_RESET}",
        )

        if inventory == 0:
            self.logger.warning(
                f"{COLOR_YELLOW}No open position to exit. Signal ignored.{COLOR_RESET}",
            )
            return False

        side_for_exit = "Sell" if inventory > 0 else "Buy"
        exit_quantity = abs(inventory)

        exit_order_kwargs = {
            "category": config.BYBIT_CATEGORY,
            "symbol": config.SYMBOL,
            "side": side_for_exit,
            "order_type": "Market",
            "qty": f"{exit_quantity:.8f}",
        }
        if config.HEDGE_MODE:
            exit_order_kwargs["positionIdx"] = 1 if side_for_exit == "Buy" else 2
        else:
            exit_order_kwargs["positionIdx"] = 0

        self.logger.info(
            f"{PYRMETHUS_ORANGE}Placing {side_for_exit} Market exit for {exit_quantity:.4f} {config.SYMBOL}{COLOR_RESET}",
        )

        try:
            response = await self.bybit_client.create_order(**exit_order_kwargs)
            if response and response.get("retCode") == 0:
                self.logger.info(
                    f"{PYRMETHUS_GREEN}Successfully placed exit order.{COLOR_RESET}",
                )
                # The main bot loop will handle the position state reset via WebSocket updates.
                return True
            self.logger.error(
                f"{COLOR_RED}Exit order failed. Response: {response.get('retMsg', 'Unknown error')}{COLOR_RESET}",
            )
            return False
        except BybitAPIError as e:
            await self.bot._handle_api_error(e, "exit order placement")
            return False
        except Exception as e:
            log_exception(self.logger, "Exception during exit order placement", e)
            return False

    async def chase_limit_order(
        self,
        order_id: str,
        symbol: str,
        side: str,
        chase_aggressiveness: float = 0.0005,
    ):
        """Monitors and amends a limit order to keep it competitive."""
        self.logger.info(
            f"{PYRMETHUS_ORANGE}Chasing limit order {order_id} for {symbol}...{COLOR_RESET}",
        )
        max_amendments = 10
        amendment_count = 0

        while amendment_count < max_amendments:
            await asyncio.sleep(config.POLLING_INTERVAL_SECONDS)
            try:
                order_status_resp = await self.bybit_client.get_order_status(
                    category=config.BYBIT_CATEGORY, order_id=order_id, symbol=symbol,
                )
                order_status = order_status_resp.get("result", {}).get("list", [{}])[0]
                if order_status.get("orderStatus") not in ["New", "PartiallyFilled"]:
                    self.logger.info(
                        f"{PYRMETHUS_GREEN}Order {order_id} is no longer active ({order_status.get('orderStatus')}). Stopping chase.{COLOR_RESET}",
                    )
                    break

                order_book_resp = await self.bybit_client.get_orderbook(
                    category=config.BYBIT_CATEGORY, symbol=symbol,
                )
                if not order_book_resp or order_book_resp.get("retCode") != 0:
                    self.logger.warning(
                        f"{COLOR_YELLOW}Could not fetch order book for chasing.{COLOR_RESET}",
                    )
                    continue

                best_bid = Decimal(order_book_resp["result"]["b"][0][0])
                best_ask = Decimal(order_book_resp["result"]["a"][0][0])
                current_limit_price = Decimal(order_status["price"])

                new_price = None
                if side == "Buy" and current_limit_price < best_bid:
                    new_price = best_bid
                elif side == "Sell" and current_limit_price > best_ask:
                    new_price = best_ask

                if new_price:
                    amendment_result = await self.bybit_client.amend_order(
                        category=config.BYBIT_CATEGORY,
                        symbol=symbol,
                        orderId=order_id,
                        price=f"{new_price:.4f}",
                    )
                    if amendment_result and amendment_result.get("retCode") == 0:
                        self.logger.info(
                            f"{PYRMETHUS_BLUE}Amended order {order_id} to new price {new_price:.4f}{COLOR_RESET}",
                        )
                        amendment_count += 1
                    else:
                        self.logger.error(
                            f"{COLOR_RED}Failed to amend order {order_id}: {amendment_result.get('retMsg', 'N/A')}{COLOR_RESET}",
                        )

            except BybitAPIError as e:
                if e.ret_code in [10009, 110001]:  # Order not found
                    self.logger.info(
                        f"Order {order_id} not found, assuming it was filled or cancelled.",
                    )
                    break
                await self.bot._handle_api_error(e, f"chasing order {order_id}")
            except Exception as e:
                log_exception(self.logger, f"Error chasing order {order_id}", e)

        if amendment_count >= max_amendments:
            self.logger.warning(
                f"{COLOR_YELLOW}Reached max amendments for order {order_id}. Stopping chase.{COLOR_RESET}",
            )
