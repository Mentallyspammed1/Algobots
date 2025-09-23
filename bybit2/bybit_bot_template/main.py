import asyncio
import os
import sys
from dotenv import load_dotenv
from loguru import logger

# Import custom modules
from api.bybit_client import BybitClient
from config import STRATEGY_NAME, LOG_LEVEL, LOG_FILE, STRATEGY_PARAMS
from strategies.strategy_base import StrategyBase
from utils.logger import setup_logger
from utils.indicators import calculate_sma # Example indicator import

# --- Pyrmethus Persona Integration ---
from colorama import Fore, Style, init
init(autoreset=True)

# --- Load Environment Variables ---
load_dotenv()

# --- Setup Logging ---
setup_logger(log_level=LOG_LEVEL, log_file=LOG_FILE)

# --- Dynamic Strategy Loading ---
def load_strategy(strategy_name: str, client: BybitClient, state: dict, params: dict) -> StrategyBase:
    """Dynamically loads a trading strategy based on its name."""
    try:
        # Dynamically import the strategy module
        # Assumes strategy files are in the 'strategies' directory and named like 'strategy_name.py'
        module_name = f"strategies.{strategy_name.lower()}"
        strategy_module = __import__(module_name, fromlist=['Strategy'])
        
        # Instantiate the strategy class (assuming it's named 'Strategy' or similar)
        # We need to find the correct class name within the module.
        # A common convention is to name the class after the strategy, e.g., 'ExampleStrategy'
        strategy_class_name = f"{strategy_name}" # e.g., "ExampleStrategy"
        StrategyClass = getattr(strategy_module, strategy_class_name)
        
        logger.info(f"Instantiating strategy: {strategy_class_name}")
        return StrategyClass(client=client, state=state, params=params)
    except ImportError:
        logger.error(f"Strategy module '{module_name}' not found.")
        sys.exit(1)
    except AttributeError:
        logger.error(f"Strategy class '{strategy_class_name}' not found in module '{module_name}'.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading strategy '{strategy_name}': {e}")
        sys.exit(1)

# --- Main Bot Logic ---
async def run_bot():
    """Initializes and runs the trading bot."""
    logger.info(f"Starting {Fore.CYAN}{BOT_NAME}{Style.RESET_ALL}...")

    # --- Initialize Bybit Client ---
    try:
        bybit_client = BybitClient()
        await bybit_client.initialize() # Async initialization
    except Exception as e:
        logger.critical(f"Failed to initialize Bybit client: {e}")
        sys.exit(1)

    # --- Initialize Bot State ---
    # This state will be shared between the bot and the strategy
    bot_state = {
        "current_position": None, # e.g., {"symbol": "BTCUSDT", "side": "Buy", "size": "0.001", "entry_price": "40000"}
        "open_orders": [],
        "unrealized_pnl": 0.0,
        "last_kline_time": None,
        "strategy_specific_state": {} # For strategy-specific data
    }

    # --- Load Trading Strategy ---
    logger.info(f"Loading strategy: {Fore.CYAN}{STRATEGY_NAME}{Style.RESET_ALL}")
    # Pass strategy-specific parameters
    strategy = load_strategy(STRATEGY_NAME, bybit_client, bot_state, STRATEGY_PARAMS)
    if not isinstance(strategy, StrategyBase):
        logger.error("Loaded strategy is not an instance of StrategyBase.")
        sys.exit(1)

    # --- Start WebSocket Listeners and Main Loop ---
    logger.info("Starting WebSocket listeners and main bot loop...")
    
    # Example: Subscribe to kline data for the strategy's symbol
    symbol = STRATEGY_PARAMS.get("symbol", "BTCUSDT")
    interval = STRATEGY_PARAMS.get("interval", "1")
    kline_topic = f"kline.{interval}.{symbol}"
    
    # Start WebSocket client and subscribe to relevant topics
    await bybit_client.start_websocket([kline_topic, f"position.{symbol}"]) # Subscribe to klines and positions

    # Main loop to process events and run strategy logic
    while True:
        try:
            # Process incoming WebSocket messages
            await bybit_client.process_websocket_messages()

            # Execute strategy logic based on received data or on a schedule
            # For simplicity, we'll trigger strategy logic when new kline data is available
            # A more sophisticated bot might use scheduled tasks or event-driven triggers
            
            # Check if new kline data is available and process it
            new_kline_data = bybit_client.get_latest_kline(symbol, interval)
            if new_kline_data and new_kline_data.get("timestamp") != bot_state.get("last_kline_time"):
                logger.debug(f"Processing new kline for {symbol} at {new_kline_data.get('timestamp')}")
                bot_state["last_kline_time"] = new_kline_data.get("timestamp")
                
                # Update bot state with latest kline data if needed by strategy
                # bot_state["latest_kline"] = new_kline_data 
                
                # Call strategy's kline processing method
                await strategy.on_kline(new_kline_data)

            # Process position updates
            position_update = bybit_client.get_latest_position(symbol)
            if position_update and position_update.get("update_time") != bot_state.get("last_position_update_time"):
                logger.debug(f"Processing position update for {symbol}")
                bot_state["last_position_update_time"] = position_update.get("update_time")
                await strategy.on_position_update(position_update)

            # Add other event processing or scheduled tasks here
            # e.g., checking open orders, managing TP/SL, rebalancing, etc.

            await asyncio.sleep(0.1) # Small sleep to prevent busy-waiting

        except asyncio.CancelledError:
            logger.info("Bot task cancelled. Shutting down...")
            break
        except Exception as e:
            logger.error(f"An unexpected error occurred in the main loop: {e}")
            # Implement more robust error handling, e.g., exponential backoff for retries
            await asyncio.sleep(5) # Wait before retrying

    logger.info("Bot has shut down.")

if __name__ == "__main__":
    # --- Pyrmethus Persona: Setup check ---
    print(Fore.MAGENTA + "# Pyrmethus, the Termux Coding Wizard, channeling the bot's essence... #" + Style.RESET_ALL)
    
    # --- Create dummy files if they don't exist for demonstration ---
    # Ensure .env exists
    env_file_path = '/data/data/com.termux/files/home/Algobots/bybit2/bybit_bot_template/.env'
    if not os.path.exists(env_file_path):
        with open(env_file_path, 'w') as f:
            f.write('BYBIT_API_KEY=YOUR_API_KEY_HERE\n')
            f.write('BYBIT_API_SECRET=YOUR_API_SECRET_HERE\n')
            f.write('BYBIT_TESTNET=True\n')
        logger.warning(f"Created dummy '{env_file_path}'. Please fill in your API keys.")

    # Ensure strategy files exist (at least the base and example)
    strategies_dir = '/data/data/com.termux/files/home/Algobots/bybit2/bybit_bot_template/strategies'
    if not os.path.exists(os.path.join(strategies_dir, 'strategy_base.py')):
        with open(os.path.join(strategies_dir, 'strategy_base.py'), 'w') as f:
            f.write('''
import asyncio
from abc import ABC, abstractmethod

class StrategyBase(ABC):
    def __init__(self, client, state, params):
        self.client = client
        self.state = state
        self.params = params
        self.logger = self.client.logger # Access logger from client

    @abstractmethod
    async def on_kline(self, kline_data):
        pass

    @abstractmethod
    async def on_position_update(self, position_data):
        pass

    async def on_order_update(self, order_data):
        # Default implementation does nothing, can be overridden
        pass

    async def generate_signals(self):
        # This method would contain the core trading logic
        pass
            ''')
        logger.warning(f