import json
import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pandas as pd
from colorama import Fore, Style, init
from pybit.exceptions import PybitAPIException
from pybit.unified_trading import HTTP, WebSocket
from pydantic import BaseModel, ValidationError

try:
    from dotenv import load_dotenv
except ImportError:
    print(f"{Fore.YELLOW}Warning: 'python-dotenv' not found. Please install it: pip install python-dotenv{Style.RESET_ALL}")
    def load_dotenv(): pass

init(autoreset=True)
load_dotenv()

# --- Constants and Configuration ---
NG, NB, NP, NY, NR, NC, RST = (
    Fore.LIGHTGREEN_EX + Style.BRIGHT,
    Fore.CYAN + Style.BRIGHT,
    Fore.MAGENTA + Style.BRIGHT,
    Fore.YELLOW + Style.BRIGHT,
    Fore.LIGHTRED_EX + Style.BRIGHT,
    Fore.CYAN + Style.BRIGHT,
    Style.RESET_ALL,
)

AK: str | None = os.getenv("BYBIT_API_KEY")
AS: str | None = os.getenv("BYBIT_API_SECRET")
WEBHOOK_PASSPHRASE: str | None = os.getenv("WEBHOOK_PASSPHRASE")

LD: Path = Path("bot_logs")
LD.mkdir(parents=True, exist_ok=True)

# --- Pydantic Models for Signal Validation ---
class TradeSignal(BaseModel):
    passphrase: str
    strategy_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    leverage: int | None = None

# --- Utility Functions ---
def setup_logger(name_suffix: str) -> logging.Logger:
    logger = logging.getLogger(f"webhook_bot_{name_suffix}")
    if logger.hasHandlers():
        return logger
    logger.setLevel(logging.INFO)
    log_file_path = LD / f"webhook_bot_{name_suffix}.log"
    file_handler = RotatingFileHandler(log_file_path, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
    file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_formatter = logging.Formatter("%(asctime)s - %(levelname)-8s - [%(name)s] - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger

# --- WebSocket Manager ---
class BybitWebSocketManager:
    def __init__(self, api_key: str, api_secret: str, symbols: list[str], kline_interval: str, logger: logging.Logger):
        self.ws = WebSocket(testnet=True, channel_type="linear", api_key=api_key, api_secret=api_secret)
        self.symbols = symbols
        self.kline_interval = kline_interval
        self.logger = logger
        self.kline_data: dict[str, pd.DataFrame] = {}
        self.ws = WebSocket(testnet=True, channel_type="linear", api_key=api_key, api_secret=api_secret)
        self.symbols = symbols
        self.logger = logger

    def start(self):
        for symbol in self.symbols:
            self.ws.orderbook_stream(depth=1, symbol=symbol.replace("/", "").replace(":USDT", ""), callback=self.handle_orderbook)
        self.logger.info("WebSocket streams started.")

    def handle_orderbook(self, message: dict):
        self.logger.debug(f"Received orderbook update: {message}")

# --- Trading Bot Class ---

class TradingBot:
    def __init__(self):
        self.logger = setup_logger("main")
        self.config = self._load_config()
        self.session = self.initialize_session()
        self.symbol_configs = self._load_symbol_configs()
        self.ws_manager = BybitWebSocketManager(AK, AS, list(self.symbol_configs.keys()), self.logger)
        threading.Thread(target=self.ws_manager.start, daemon=True).start()

    def process_strategy_signal(self, raw_webhook_data: dict) -> TradeSignal | None:
        """This method is the entry point for your custom trading strategy.
        It receives raw webhook data and should return a TradeSignal object
        if a trade is to be executed, or None otherwise.

        Implement your strategy logic here.
        """
        self.logger.info(f"Processing raw webhook data for strategy: {raw_webhook_data}")

        # --- Placeholder for your strategy logic ---
        # Example: You might parse the raw_webhook_data, check indicators,
        # and decide to create a TradeSignal.
        # For now, it attempts to create a TradeSignal directly from the raw data
        # as if the webhook itself is the signal.
        try:
            signal = TradeSignal(**raw_webhook_data)
            self.logger.info(f"Successfully parsed TradeSignal: {signal.strategy_id}")
            return signal
        except ValidationError as e:
            self.logger.error(f"Raw webhook data does not conform to TradeSignal format: {e.errors()}")
            return None
        # --- End of strategy logic placeholder ---

    def _load_config(self) -> dict:
        try:
            with open("config.json") as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.error("config.json not found. Please create it.")
            sys.exit(1)
        except json.JSONDecodeError:
            self.logger.error("Error decoding config.json. Please check its format.")
            sys.exit(1)

    testnet_from_env = os.getenv("BYBIT_TESTNET")
        testnet_from_config = self.config.get("testnet")

        if testnet_from_env is not None:
            self.testnet = testnet_from_env.lower() in ("true", "1", "yes")
        elif testnet_from_config is not None:
            self.testnet = testnet_from_config
        else:
            self.testnet = True # Default to testnet if not specified

        self.logger.info(f"Bybit session initialized in {'testnet' if self.testnet else 'live'} mode.")
        return session

    def _load_symbol_configs(self) -> dict[str, dict]:
        symbol_configs = {}
        for item in self.config.get("symbols", []):
            symbol_configs[item["symbol"]] = item
        if not symbol_configs:
            self.logger.warning("No symbols found in config.json. Trading functionality may be limited.")
        return symbol_configs

    def execute_trade(self, signal: TradeSignal) -> dict:
        symbol_pybit = signal.symbol.replace("/", "").replace(":USDT", "")
        symbol_config = self.symbol_configs.get(signal.symbol)

        if not symbol_config:
            self.logger.error(f"Configuration for symbol {signal.symbol} not found.")
            return {"status": "error", "message": f"Configuration for symbol {signal.symbol} not found."}

        # --- Dry Run Mode ---
        dry_run_env = os.getenv("DRY_RUN")
        dry_run_config = self.config.get("dry_run")

        self.dry_run = False
        if dry_run_env is not None:
            self.dry_run = dry_run_env.lower() in ("true", "1", "yes")
        elif dry_run_config is not None:
            self.dry_run = dry_run_config
        
        if self.dry_run:
            self.logger.warning(f"DRY RUN MODE ENABLED: Simulating trade for {signal.symbol} {signal.side} {signal.quantity} {signal.order_type}")
            # Simulate a successful order placement for dry run
            simulated_order = {
                "orderId": f"dry_run_{signal.strategy_id}_{int(time.time())}",
                "symbol": symbol_pybit,
                "side": signal.side.capitalize(),
                "orderType": signal.order_type.capitalize(),
                "qty": str(signal.quantity),
                "status": "New",
                "timeInForce": "GTC",
                "createType": "CreateBySystem",
                "orderLinkId": f"dry_run_{signal.strategy_id}"
            }
            if signal.price:
                simulated_order["price"] = str(signal.price)
            if signal.stop_loss:
                simulated_order["stopLoss"] = str(signal.stop_loss)
            if signal.take_profit:
                simulated_order["takeProfit"] = str(signal.take_profit)
            
            self.logger.info(f"Simulated order placement: {simulated_order}")
            return {"status": "success", "simulated_order": simulated_order}
        # --- End Dry Run Mode ---

        try:
            if signal.leverage:
                self.session.set_leverage(category="linear", symbol=symbol_pybit, buyLeverage=str(signal.leverage), sellLeverage=str(signal.leverage))
                self.logger.info(f"Leverage set to {signal.leverage} for {signal.symbol}")

            order_params = {
                "category": "linear",
                "symbol": symbol_pybit,
                "side": signal.side.capitalize(),
                "orderType": signal.order_type.capitalize(),
                "qty": str(signal.quantity),
            }

            if signal.order_type == "limit":
                if not signal.price:
                    self.logger.error("Price is required for limit orders.")
                    return {"status": "error", "message": "Price is required for limit orders"}
                order_params["price"] = str(signal.price)

            # Calculate dynamic Stop Loss and Take Profit based on percentages
            base_price = signal.price if signal.price else self._get_current_market_price(symbol_pybit) # Placeholder for market price

            if base_price:
                if signal.side.lower() == "buy":
                    if symbol_config.get("stop_loss_percentage") and not signal.stop_loss:
                        order_params["stopLoss"] = str(base_price * (1 - symbol_config["stop_loss_percentage"])) # For buy, SL is below entry
                        self.logger.info(f"Calculated SL for {signal.symbol}: {order_params['stopLoss']}")
                    if symbol_config.get("take_profit_percentage") and not signal.take_profit:
                        order_params["takeProfit"] = str(base_price * (1 + symbol_config["take_profit_percentage"])) # For buy, TP is above entry
                        self.logger.info(f"Calculated TP for {signal.symbol}: {order_params['takeProfit']}")
                elif signal.side.lower() == "sell":
                    if symbol_config.get("stop_loss_percentage") and not signal.stop_loss:
                        order_params["stopLoss"] = str(base_price * (1 + symbol_config["stop_loss_percentage"])) # For sell, SL is above entry
                        self.logger.info(f"Calculated SL for {signal.symbol}: {order_params['stopLoss']}")
                    if symbol_config.get("take_profit_percentage") and not signal.take_profit:
                        order_params["takeProfit"] = str(base_price * (1 - symbol_config["take_profit_percentage"])) # For sell, TP is below entry
                        self.logger.info(f"Calculated TP for {signal.symbol}: {order_params['takeProfit']}")

            placed_order = self.session.place_order(**order_params)
            self.logger.info(f"Successfully placed order: {placed_order}")
            return {"status": "success", "order": placed_order}
        except PybitAPIException as e:
            self.logger.error(f"Bybit API Error for signal {signal.strategy_id}: {e.status_code} - {e.message}")
            return {"status": "error", "message": f"Bybit API Error: {e.message}", "code": e.status_code}
        except Exception as e:
            self.logger.error(f"Unexpected error executing trade for signal {signal.strategy_id}: {e}")
            return {"status": "error", "message": str(e)}

    def get_open_positions(self, symbol: str | None = None) -> dict:
        try:
            params = {"category": "linear"}
            if symbol:
                params["symbol"] = symbol.replace("/", "").replace(":USDT", "")

            response = self.session.get_positions(**params)
            if response["retCode"] == 0:
                self.logger.info(f"Fetched open positions: {response['result']['list']}")
                return {"status": "success", "positions": response["result"]["list"]}
            self.logger.error(f"Error fetching open positions: {response['retMsg']}")
            return {"status": "error", "message": response["retMsg"]}
        except PybitAPIException as e:
            self.logger.error(f"Bybit API Error fetching positions: {e.status_code} - {e.message}")
            return {"status": "error", "message": f"Bybit API Error: {e.message}", "code": e.status_code}
        except Exception as e:
            self.logger.error(f"Unexpected error fetching positions: {e}")
            return {"status": "error", "message": str(e)}

    def close_position(self, symbol: str, side: str, quantity: float) -> dict:
        try:
            symbol_pybit = symbol.replace("/", "").replace(":USDT", "")
            # To close a position, you place an order with the opposite side and the same quantity
            # For simplicity, this assumes a market order to close.
            order_params = {
                "category": "linear",
                "symbol": symbol_pybit,
                "side": "Sell" if side.lower() == "buy" else "Buy", # Opposite side
                "orderType": "Market",
                "qty": str(quantity),
                "reduceOnly": True # Ensure it only reduces position
            }
            placed_order = self.session.place_order(**order_params)
            self.logger.info(f"Successfully placed close order for {symbol}: {placed_order}")
            return {"status": "success", "order": placed_order}
        except PybitAPIException as e:
            self.logger.error(f"Bybit API Error closing position for {symbol}: {e.status_code} - {e.message}")
            return {"status": "error", "message": f"Bybit API Error: {e.message}", "code": e.status_code}
        except Exception as e:
            self.logger.error(f"Unexpected error closing position for {symbol}: {e}")
            return {"status": "error", "message": str(e)}

    def amend_order(self, order_id: str, symbol: str, new_price: float | None = None, new_quantity: float | None = None) -> dict:
        try:
            symbol_pybit = symbol.replace("/", "").replace(":USDT", "")
            amend_params = {
                "category": "linear",
                "symbol": symbol_pybit,
                "orderId": order_id
            }
            if new_price is not None:
                amend_params["price"] = str(new_price)
            if new_quantity is not None:
                amend_params["qty"] = str(new_quantity)

            if not new_price and not new_quantity:
                return {"status": "error", "message": "Either new_price or new_quantity must be provided to amend an order."}

            amended_order = self.session.amend_order(**amend_params)
            self.logger.info(f"Successfully amended order {order_id} for {symbol}: {amended_order}")
            return {"status": "success", "order": amended_order}
        except PybitAPIException as e:
            self.logger.error(f"Bybit API Error amending order {order_id} for {symbol}: {e.status_code} - {e.message}")
            return {"status": "error", "message": f"Bybit API Error: {e.message}", "code": e.status_code}
        except Exception as e:
            self.logger.error(f"Unexpected error amending order {order_id} for {symbol}: {e}")
            return {"status": "error", "message": str(e)}

    def _get_current_market_price(self, symbol: str) -> float | None:
        try:
            response = self.session.get_tickers(category="linear", symbol=symbol)
            if response and response["retCode"] == 0 and response["result"]["list"]:
                # Assuming the first ticker in the list is the relevant one
                last_price = float(response["result"]["list"][0]["lastPrice"])
                self.logger.info(f"Fetched current market price for {symbol}: {last_price}")
                return last_price
            self.logger.warning(f"Could not fetch current market price for {symbol}. Response: {response}")
            return None
        except PybitAPIException as e:
            self.logger.error(f"Error fetching market price for {symbol}: {e.message}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error fetching market price for {symbol}: {e}")
            return None

    def _load_symbol_configs(self) -> dict[str, dict]:
        symbol_configs = {}
        for item in self.config.get("symbols", []):
            symbol_configs[item["symbol"]] = item
        if not symbol_configs:
            self.logger.warning("No symbols found in config.json. Trading functionality may be limited.")
        return symbol_configs

    def execute_trade(self, signal: TradeSignal) -> dict:
        symbol_pybit = signal.symbol.replace("/", "").replace(":USDT", "")
        symbol_config = self.symbol_configs.get(signal.symbol)

        if not symbol_config:
            self.logger.error(f"Configuration for symbol {signal.symbol} not found.")
            return {"status": "error", "message": f"Configuration for symbol {signal.symbol} not found."}

        try:
            if signal.leverage:
                self.session.set_leverage(category="linear", symbol=symbol_pybit, buyLeverage=str(signal.leverage), sellLeverage=str(signal.leverage))
                self.logger.info(f"Leverage set to {signal.leverage} for {signal.symbol}")

            order_params = {
                "category": "linear",
                "symbol": symbol_pybit,
                "side": signal.side.capitalize(),
                "orderType": signal.order_type.capitalize(),
                "qty": str(signal.quantity),
            }

            if signal.order_type == "limit":
                if not signal.price:
                    self.logger.error("Price is required for limit orders.")
                    return {"status": "error", "message": "Price is required for limit orders"}
                order_params["price"] = str(signal.price)

            # Calculate dynamic Stop Loss and Take Profit based on percentages
            base_price = signal.price if signal.price else self._get_current_market_price(symbol_pybit) # Placeholder for market price

            if base_price:
                if signal.side.lower() == "buy":
                    if symbol_config.get("stop_loss_percentage") and not signal.stop_loss:
                        order_params["stopLoss"] = str(base_price * (1 - symbol_config["stop_loss_percentage"])) # For buy, SL is below entry
                        self.logger.info(f"Calculated SL for {signal.symbol}: {order_params['stopLoss']}")
                    if symbol_config.get("take_profit_percentage") and not signal.take_profit:
                        order_params["takeProfit"] = str(base_price * (1 + symbol_config["take_profit_percentage"])) # For buy, TP is above entry
                        self.logger.info(f"Calculated TP for {signal.symbol}: {order_params['takeProfit']}")
                elif signal.side.lower() == "sell":
                    if symbol_config.get("stop_loss_percentage") and not signal.stop_loss:
                        order_params["stopLoss"] = str(base_price * (1 + symbol_config["stop_loss_percentage"])) # For sell, SL is above entry
                        self.logger.info(f"Calculated SL for {signal.symbol}: {order_params['stopLoss']}")
                    if symbol_config.get("take_profit_percentage") and not signal.take_profit:
                        order_params["takeProfit"] = str(base_price * (1 - symbol_config["take_profit_percentage"])) # For sell, TP is below entry
                        self.logger.info(f"Calculated TP for {signal.symbol}: {order_params['takeProfit']}")

            placed_order = self.session.place_order(**order_params)
            self.logger.info(f"Successfully placed order: {placed_order}")
            return {"status": "success", "order": placed_order}
        except PybitAPIException as e:
            self.logger.error(f"Bybit API Error for signal {signal.strategy_id}: {e.status_code} - {e.message}")
            return {"status": "error", "message": f"Bybit API Error: {e.message}", "code": e.status_code}
        except Exception as e:
            self.logger.error(f"Unexpected error executing trade for signal {signal.strategy_id}: {e}")
            return {"status": "error", "message": str(e)}

    def get_open_positions(self, symbol: str | None = None) -> dict:
        try:
            params = {"category": "linear"}
            if symbol:
                params["symbol"] = symbol.replace("/", "").replace(":USDT", "")

            response = self.session.get_positions(**params)
            if response["retCode"] == 0:
                self.logger.info(f"Fetched open positions: {response['result']['list']}")
                return {"status": "success", "positions": response["result"]["list"]}
            self.logger.error(f"Error fetching open positions: {response['retMsg']}")
            return {"status": "error", "message": response["retMsg"]}
        except PybitAPIException as e:
            self.logger.error(f"Bybit API Error fetching positions: {e.status_code} - {e.message}")
            return {"status": "error", "message": f"Bybit API Error: {e.message}", "code": e.status_code}
        except Exception as e:
            self.logger.error(f"Unexpected error fetching positions: {e}")
            return {"status": "error", "message": str(e)}

    def close_position(self, symbol: str, side: str, quantity: float) -> dict:
        try:
            symbol_pybit = symbol.replace("/", "").replace(":USDT", "")
            # To close a position, you place an order with the opposite side and the same quantity
            # For simplicity, this assumes a market order to close.
            order_params = {
                "category": "linear",
                "symbol": symbol_pybit,
                "side": "Sell" if side.lower() == "buy" else "Buy", # Opposite side
                "orderType": "Market",
                "qty": str(quantity),
                "reduceOnly": True # Ensure it only reduces position
            }
            placed_order = self.session.place_order(**order_params)
            self.logger.info(f"Successfully placed close order for {symbol}: {placed_order}")
            return {"status": "success", "order": placed_order}
        except PybitAPIException as e:
            self.logger.error(f"Bybit API Error closing position for {symbol}: {e.status_code} - {e.message}")
            return {"status": "error", "message": f"Bybit API Error: {e.message}", "code": e.status_code}
        except Exception as e:
            self.logger.error(f"Unexpected error closing position for {symbol}: {e}")
            return {"status": "error", "message": str(e)}

    def amend_order(self, order_id: str, symbol: str, new_price: float | None = None, new_quantity: float | None = None) -> dict:
        try:
            symbol_pybit = symbol.replace("/", "").replace(":USDT", "")
            amend_params = {
                "category": "linear",
                "symbol": symbol_pybit,
                "orderId": order_id
            }
            if new_price is not None:
                amend_params["price"] = str(new_price)
            if new_quantity is not None:
                amend_params["qty"] = str(new_quantity)

            if not new_price and not new_quantity:
                return {"status": "error", "message": "Either new_price or new_quantity must be provided to amend an order."}

            amended_order = self.session.amend_order(**amend_params)
            self.logger.info(f"Successfully amended order {order_id} for {symbol}: {amended_order}")
            return {"status": "success", "order": amended_order}
        except PybitAPIException as e:
            self.logger.error(f"Bybit API Error amending order {order_id} for {symbol}: {e.status_code} - {e.message}")
            return {"status": "error", "message": f"Bybit API Error: {e.message}", "code": e.status_code}
        except Exception as e:
            self.logger.error(f"Unexpected error amending order {order_id} for {symbol}: {e}")
            return {"status": "error", "message": str(e)}

    def _get_current_market_price(self, symbol: str) -> float | None:
        try:
            response = self.session.get_tickers(category="linear", symbol=symbol)
            if response and response["retCode"] == 0 and response["result"]["list"]:
                # Assuming the first ticker in the list is the relevant one
                last_price = float(response["result"]["list"][0]["lastPrice"])
                self.logger.info(f"Fetched current market price for {symbol}: {last_price}")
                return last_price
            self.logger.warning(f"Could not fetch current market price for {symbol}. Response: {response}")
            return None
        except PybitAPIException as e:
            self.logger.error(f"Error fetching market price for {symbol}: {e.message}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error fetching market price for {symbol}: {e}")
            return None
