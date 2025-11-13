import logging
import os
import sys
import time
import uuid
from decimal import ROUND_DOWN, Decimal
from typing import Any

from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket

# Load environment variables from .env file
load_dotenv()


# --- Logging Setup ---
def setup_logging():
    """Configure logging with file and console handlers."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(module)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("marketmaker.log", mode="a"),
        ],
    )
    return logging.getLogger(__name__)


logger = setup_logging()


# --- Configuration ---
class Config:
    def __init__(self):
        # Load required environment variables
        self.API_KEY = self._get_env_var("BYBIT_API_KEY")
        self.API_SECRET = self._get_env_var("BYBIT_API_SECRET")
        self.TESTNET = os.getenv("BYBIT_TESTNET", "False").lower() in ("true", "1", "t")
        self.SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
        self.CATEGORY = os.getenv("CATEGORY", "linear")

        # Load optional parameters with defaults
        self.BASE_SPREAD_BPS = Decimal(os.getenv("BASE_SPREAD_BPS", "50"))  # 0.5%
        self.MIN_SPREAD_TICKS = Decimal(os.getenv("MIN_SPREAD_TICKS", "1"))
        self.RISK_PER_TRADE_PCT = Decimal(os.getenv("RISK_PER_TRADE_PCT", "1"))  # 1%
        self.LEVERAGE = Decimal(os.getenv("LEVERAGE", "1"))
        self.ACCOUNT_BALANCE = Decimal(os.getenv("ACCOUNT_BALANCE", "10000"))
        self.POST_ONLY = os.getenv("POST_ONLY", "True").lower() in ("true", "1", "t")
        self.REPLACE_THRESHOLD_TICKS = Decimal(
            os.getenv("REPLACE_THRESHOLD_TICKS", "5")
        )
        self.PROTECT_MODE = os.getenv(
            "PROTECT_MODE", "off"
        )  # "off", "trailing", "breakeven"
        self.TRAILING_DISTANCE = Decimal(os.getenv("TRAILING_DISTANCE", "10"))
        self.TRAILING_ACTIVATE_PROFIT_BPS = Decimal(
            os.getenv("TRAILING_ACTIVATE_PROFIT_BPS", "100")
        )  # 1%
        self.BE_TRIGGER_BPS = Decimal(os.getenv("BE_TRIGGER_BPS", "200"))  # 2%
        self.BE_OFFSET_TICKS = Decimal(os.getenv("BE_OFFSET_TICKS", "2"))

        # Validate required environment variables
        self._validate_required_vars()

    def _get_env_var(self, var_name: str) -> str:
        """Get environment variable with error handling."""
        value = os.getenv(var_name)
        if value is None:
            logger.critical(f"Missing required environment variable: {var_name}")
            sys.exit(1)
        return value

    def _validate_required_vars(self):
        """Validate that all required environment variables are set."""
        required_vars = ["BYBIT_API_KEY", "BYBIT_API_SECRET", "SYMBOL", "CATEGORY"]
        for var in required_vars:
            if not getattr(self, var.replace("BYBIT_", "").replace("_", "").upper()):
                logger.critical(f"Missing required environment variable: {var}")
                sys.exit(1)


# --- Helpers ---
def q_round(v: Decimal, step: Decimal) -> Decimal:
    """Round a Decimal value to the nearest step."""
    n = (v / step).to_integral_value(rounding=ROUND_DOWN)
    return (n * step).normalize()


# --- REST API Wrapper ---
class BybitRest:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = HTTP(
            testnet=cfg.TESTNET, api_key=cfg.API_KEY, api_secret=cfg.API_SECRET
        )
        self.load_instrument()

    def load_instrument(self):
        """Load instrument details from the exchange."""
        try:
            response = self.client.get_instruments_info(
                category=self.cfg.CATEGORY, symbol=self.cfg.SYMBOL
            )
            if response["retCode"] != 0:
                logger.error(f"API Error: {response.get('retMsg', 'Unknown error')}")
                sys.exit(1)

            item = response["result"]["list"][0]
            self.tick_size = Decimal(item["priceFilter"]["tickSize"])
            lot = item["lotSizeFilter"]
            self.lot_size = Decimal(lot.get("qtyStep", "0.001"))
            self.min_notional = Decimal(lot.get("minOrderAmt", "0"))
            self.min_qty = Decimal(lot.get("minOrderQty", "0"))
            self.max_qty = Decimal(lot.get("maxOrderQty", "999999999"))
            logger.info(f"Instrument details loaded for {self.cfg.SYMBOL}")
        except Exception as e:
            logger.critical(f"Failed to load instrument details: {e}")
            sys.exit(1)

    def place_batch_order(self, orders: list[dict[str, Any]]) -> dict:
        """Place batch orders."""
        try:
            response = self.client.place_batch_order(
                category=self.cfg.CATEGORY, request=orders
            )
            if response["retCode"] != 0:
                logger.error(
                    f"Failed to place batch order: {response.get('retMsg', 'Unknown error')}"
                )
            return response
        except Exception as e:
            logger.error(f"Failed to place batch order: {e}")
            raise

    def amend_batch_order(self, orders: list[dict[str, Any]]) -> dict:
        """Amend batch orders."""
        try:
            response = self.client.amend_batch_order(
                category=self.cfg.CATEGORY, request=orders
            )
            if response["retCode"] != 0:
                logger.error(
                    f"Failed to amend batch order: {response.get('retMsg', 'Unknown error')}"
                )
            return response
        except Exception as e:
            logger.error(f"Failed to amend batch order: {e}")
            raise

    def cancel_batch_order(self, orders: list[dict[str, Any]]) -> dict:
        """Cancel batch orders."""
        try:
            response = self.client.cancel_batch_order(
                category=self.cfg.CATEGORY, request=orders
            )
            if response["retCode"] != 0:
                logger.error(
                    f"Failed to cancel batch order: {response.get('retMsg', 'Unknown error')}"
                )
            return response
        except Exception as e:
            logger.error(f"Failed to cancel batch order: {e}")
            raise

    def set_trading_stop(self, params: dict[str, Any]) -> dict:
        """Set trading stop (TP/SL/Trailing)."""
        try:
            response = self.client.set_trading_stop(params)
            if response["retCode"] != 0:
                logger.error(
                    f"Failed to set trading stop: {response.get('retMsg', 'Unknown error')}"
                )
            return response
        except Exception as e:
            logger.error(f"Failed to set trading stop: {e}")
            raise


# --- Position Sizer ---
class PositionSizer:
    def __init__(self, cfg: Config, rest: BybitRest):
        self.cfg = cfg
        self.rest = rest

    def calculate_quote_size(self, entry_price: Decimal) -> Decimal:
        """Calculate position size based on risk management."""
        try:
            risk_per_trade = self.cfg.ACCOUNT_BALANCE * (
                self.cfg.RISK_PER_TRADE_PCT / 100
            )
            stop_loss_distance = entry_price * (self.cfg.RISK_PER_TRADE_PCT / 100)
            position_size = risk_per_trade / stop_loss_distance

            # Apply leverage
            position_size *= self.cfg.LEVERAGE

            # Round to valid quantity step
            qty = q_round(position_size, self.rest.lot_size)

            # Validate against instrument limits
            qty = max(qty, self.rest.min_qty)
            qty = min(qty, self.rest.max_qty)

            # Validate against min notional
            notional = qty * entry_price
            if notional < self.rest.min_notional:
                qty = q_round(self.rest.min_notional / entry_price, self.rest.lot_size)
                qty = max(qty, self.rest.min_qty)

            return qty
        except Exception as e:
            logger.error(f"Error calculating quote size: {e}")
            return self.rest.min_qty


# --- WebSocket Handlers ---
class PublicWS:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.ws = WebSocket(testnet=cfg.TESTNET, channel_type=cfg.CATEGORY)
        self.best_bid = Decimal("0")
        self.best_ask = Decimal("0")
        self.ws.orderbook_stream(symbol=cfg.SYMBOL, callback=self.on_orderbook)
        logger.info("Public WebSocket initialized")

    def on_orderbook(self, message: dict):
        """Handle order book updates."""
        try:
            data = message.get("data", [])
            if data:
                bids = data[0].get("b", [])
                asks = data[0].get("a", [])
                if bids:
                    self.best_bid = Decimal(bids[0][0])
                if asks:
                    self.best_ask = Decimal(asks[0][0])
                logger.debug(
                    f"Order book updated: Bid={self.best_bid}, Ask={self.best_ask}"
                )
        except Exception as e:
            logger.error(f"Error processing order book: {e}")

    def mid_price(self) -> Decimal:
        """Calculate mid price."""
        return (self.best_bid + self.best_ask) / 2


class PrivateWS:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.ws = WebSocket(
            testnet=cfg.TESTNET,
            channel_type="private",
            api_key=cfg.API_KEY,
            api_secret=cfg.API_SECRET,
        )
        self.position = Decimal("0")
        self.entry_price = Decimal("0")
        self.ws.position_stream(callback=self.on_position)
        self.orders: dict[str, dict] = {}
        self.ws.order_stream(callback=self.on_order)
        logger.info("Private WebSocket initialized")

    def on_position(self, message: dict):
        """Handle position updates."""
        try:
            data = message.get("data", [])
            if data:
                position = data[0]
                if position["symbol"] == self.cfg.SYMBOL:
                    self.position = Decimal(position["size"])
                    self.entry_price = Decimal(position["entryPrice"])
                    logger.debug(
                        f"Position updated: Size={self.position}, Entry={self.entry_price}"
                    )
        except Exception as e:
            logger.error(f"Error processing position update: {e}")

    def on_order(self, message: dict):
        """Handle order updates."""
        try:
            data = message.get("data", [])
            if data:
                order = data[0]
                order_id = order["orderId"]
                self.orders[order_id] = order
                logger.debug(
                    f"Order updated: ID={order_id}, Status={order.get('orderStatus')}"
                )
        except Exception as e:
            logger.error(f"Error processing order update: {e}")


# --- Market Maker ---
class MarketMaker:
    def __init__(
        self,
        cfg: Config,
        rest: BybitRest,
        public_ws: PublicWS,
        private_ws: PrivateWS,
        position_sizer: PositionSizer,
    ):
        self.cfg = cfg
        self.rest = rest
        self.public_ws = public_ws
        self.private_ws = private_ws
        self.position_sizer = position_sizer
        self.bid_id = str(uuid.uuid4())
        self.ask_id = str(uuid.uuid4())
        self.working_bid = None
        self.working_ask = None
        logger.info("Market Maker initialized")

    def compute_quotes(self) -> tuple[Decimal, Decimal]:
        """Compute bid and ask prices."""
        try:
            mid = self.public_ws.mid_price()
            if mid is None:
                logger.warning("Mid price is None, cannot compute quotes")
                return Decimal("0"), Decimal("0")

            half_spread = max(
                (self.cfg.BASE_SPREAD_BPS / 10000) * mid,
                self.cfg.MIN_SPREAD_TICKS * self.rest.tick_size,
            )
            bid = q_round(mid - half_spread, self.rest.tick_size)
            ask = q_round(mid + half_spread, self.rest.tick_size)

            # Ensure bid is below market bid and ask is above market ask
            if self.public_ws.best_bid and bid > self.public_ws.best_bid:
                bid = self.public_ws.best_bid
            if self.public_ws.best_ask and ask < self.public_ws.best_ask:
                ask = self.public_ws.best_ask

            # Ensure bid < ask
            if bid >= ask:
                spread = (ask - bid) if (ask - bid) > 0 else self.rest.tick_size
                bid = mid - (spread / 2)
                ask = mid + (spread / 2)
                bid = q_round(bid, self.rest.tick_size)
                ask = q_round(ask, self.rest.tick_size)

            logger.debug(f"Computed quotes: Bid={bid}, Ask={ask}")
            return bid, ask
        except Exception as e:
            logger.error(f"Error computing quotes: {e}")
            return Decimal("0"), Decimal("0")

    def place_or_amend_orders(self):
        """Place or amend bid and ask orders."""
        try:
            bid, ask = self.compute_quotes()
            if bid == Decimal("0") or ask == Decimal("0"):
                return

            qty = self.position_sizer.calculate_quote_size(bid)
            if qty == Decimal("0"):
                logger.warning("Quote size is zero, not placing orders")
                return

            orders = []
            # Check and update bid order
            if (
                self.working_bid is None
                or abs(self.working_bid - bid)
                >= self.cfg.REPLACE_THRESHOLD_TICKS * self.rest.tick_size
            ):
                orders.append(
                    {
                        "symbol": self.cfg.SYMBOL,
                        "side": "Buy",
                        "orderType": "Limit",
                        "qty": str(qty),
                        "price": str(bid),
                        "timeInForce": "PostOnly" if self.cfg.POST_ONLY else "GTC",
                        "orderLinkId": self.bid_id,
                    }
                )
                self.working_bid = bid

            # Check and update ask order
            if (
                self.working_ask is None
                or abs(self.working_ask - ask)
                >= self.cfg.REPLACE_THRESHOLD_TICKS * self.rest.tick_size
            ):
                orders.append(
                    {
                        "symbol": self.cfg.SYMBOL,
                        "side": "Sell",
                        "orderType": "Limit",
                        "qty": str(qty),
                        "price": str(ask),
                        "timeInForce": "PostOnly" if self.cfg.POST_ONLY else "GTC",
                        "orderLinkId": self.ask_id,
                    }
                )
                self.working_ask = ask

            if orders:
                if self.working_bid and self.working_ask:
                    logger.info("Amending existing orders")
                    self.rest.amend_batch_order(orders)
                else:
                    logger.info("Placing new orders")
                    self.rest.place_batch_order(orders)
        except Exception as e:
            logger.error(f"Error placing/amending orders: {e}")

    def cancel_orders(self):
        """Cancel all active orders."""
        try:
            orders = [
                {"symbol": self.cfg.SYMBOL, "orderLinkId": self.bid_id},
                {"symbol": self.cfg.SYMBOL, "orderLinkId": self.ask_id},
            ]
            logger.info("Cancelling all active orders")
            self.rest.cancel_batch_order(orders)
            self.working_bid = None
            self.working_ask = None
        except Exception as e:
            logger.error(f"Error cancelling orders: {e}")


# --- Protection Manager ---
class ProtectionManager:
    def __init__(
        self, cfg: Config, rest: BybitRest, private_ws: PrivateWS, public_ws: PublicWS
    ):
        self.cfg = cfg
        self.rest = rest
        self.private_ws = private_ws
        self.public_ws = public_ws
        self._be_applied = False
        self._trail_applied = False

    def apply_protection(self):
        """Apply protection strategies."""
        try:
            if self.cfg.PROTECT_MODE == "off":
                return

            position = self.private_ws.position
            entry_price = self.private_ws.entry_price
            mark_price = self.public_ws.mid_price()

            if abs(position) == 0 or entry_price == 0 or mark_price == 0:
                return

            if self.cfg.PROTECT_MODE == "trailing":
                self.apply_trailing_stop(position, entry_price, mark_price)
            elif self.cfg.PROTECT_MODE == "breakeven":
                self.apply_breakeven(position, entry_price, mark_price)
        except Exception as e:
            logger.error(f"Error applying protection: {e}")

    def apply_trailing_stop(
        self, position: Decimal, entry_price: Decimal, mark_price: Decimal
    ):
        """Apply trailing stop loss."""
        try:
            long = position > 0
            distance = self.cfg.TRAILING_DISTANCE * self.rest.tick_size
            activate_profit = (
                self.cfg.TRAILING_ACTIVATE_PROFIT_BPS / 10000
            ) * entry_price

            if long:
                if mark_price >= entry_price + activate_profit:
                    self.rest.set_trading_stop(
                        {
                            "category": self.cfg.CATEGORY,
                            "symbol": self.cfg.SYMBOL,
                            "trailingStop": str(distance),
                            "activePrice": str(entry_price + activate_profit),
                            "positionIdx": 0,
                        }
                    )
                    logger.info(
                        f"Trailing stop set for long position at distance {distance}"
                    )
                    self._trail_applied = True
            else:
                if mark_price <= entry_price - activate_profit:
                    self.rest.set_trading_stop(
                        {
                            "category": self.cfg.CATEGORY,
                            "symbol": self.cfg.SYMBOL,
                            "trailingStop": str(distance),
                            "activePrice": str(entry_price - activate_profit),
                            "positionIdx": 0,
                        }
                    )
                    logger.info(
                        f"Trailing stop set for short position at distance {distance}"
                    )
                    self._trail_applied = True
        except Exception as e:
            logger.error(f"Error applying trailing stop: {e}")

    def apply_breakeven(
        self, position: Decimal, entry_price: Decimal, mark_price: Decimal
    ):
        """Apply breakeven stop loss."""
        try:
            long = position > 0
            profit_bps = (
                (mark_price / entry_price - 1) * 100
                if long
                else (1 - mark_price / entry_price) * 100
            )

            if profit_bps >= self.cfg.BE_TRIGGER_BPS:
                offset = self.cfg.BE_OFFSET_TICKS * self.rest.tick_size
                stop_price = entry_price + offset if long else entry_price - offset
                self.rest.set_trading_stop(
                    {
                        "category": self.cfg.CATEGORY,
                        "symbol": self.cfg.SYMBOL,
                        "stopLoss": str(stop_price),
                        "positionIdx": 0,
                    }
                )
                logger.info(f"Breakeven stop set at {stop_price}")
                self._be_applied = True
        except Exception as e:
            logger.error(f"Error applying breakeven stop: {e}")


# --- Main Execution ---
def main():
    try:
        # Load configuration
        cfg = Config()

        # Initialize components
        rest = BybitRest(cfg)
        public_ws = PublicWS(cfg)
        private_ws = PrivateWS(cfg)
        position_sizer = PositionSizer(cfg, rest)
        market_maker = MarketMaker(cfg, rest, public_ws, private_ws, position_sizer)
        protection_manager = ProtectionManager(cfg, rest, private_ws, public_ws)

        logger.info("Market maker started. Press Ctrl+C to stop.")

        # Main loop
        while True:
            try:
                market_maker.place_or_amend_orders()
                protection_manager.apply_protection()
                time.sleep(1)  # Adjust sleep duration as needed
            except KeyboardInterrupt:
                logger.info("Shutdown initiated by user.")
                market_maker.cancel_orders()
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(5)  # Wait before retrying

    except Exception as e:
        logger.critical(f"Fatal error in main execution: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
