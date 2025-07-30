# PSG.py - Pyrmethus's Ultra Scalper Bot (Upgraded)
import os
import asyncio
import pandas as pd
import logging
from typing import Any, Dict, List, Tuple, Union, Optional, Callable

# --- Pyrmethus's Color Codex ---
# Assuming color_codex.py is in the same directory
from color_codex import (
    COLOR_RESET, COLOR_BOLD, COLOR_DIM,
    COLOR_RED, COLOR_GREEN, COLOR_YELLOW, COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN,
    PYRMETHUS_GREEN, PYRMETHUS_BLUE, PYRMETHUS_PURPLE, PYRMETHUS_ORANGE, PYRMETHUS_GREY
)

# --- Import Configuration and Indicator Logic ---
# Assuming config.py, indicators.py, strategy.py, bybit_api.py,
# bot_logger.py, trade_metrics.py, utils.py are in the same directory
from config import (
    SYMBOL, INTERVAL, USDT_AMOUNT_PER_TRADE, PIVOT_LEFT_BARS, PIVOT_RIGHT_BARS, PIVOT_TOLERANCE_PCT,
    STOCHRSI_K_PERIOD, STOCHRSI_D_PERIOD, STOCHRSI_OVERBOUGHT_LEVEL,
    STOCHRSI_OVERSOLD_LEVEL, USE_STOCHRSI_CROSSOVER, STOP_LOSS_PCT,
    TAKE_PROFIT_PCT, BYBIT_API_ENDPOINT, BYBIT_CATEGORY, CANDLE_FETCH_LIMIT,
    POLLING_INTERVAL_SECONDS, API_REQUEST_RETRIES, API_BACKOFF_FACTOR
)
from indicators import calculate_fibonacci_pivot_points, calculate_stochrsi
from strategy import generate_signals, generate_exit_signals
from bybit_api import BybitContractAPI # The new asynchronous Bybit API client

# --- Configure Logging ---
from bot_logger import setup_logging, log_trade, log_metrics, log_exception
from trade_metrics import TradeMetrics
from utils import calculate_order_quantity

class PyrmethusBot:
    """
    The core trading bot logic, encapsulating state, API interactions,
    and trading decisions.
    """
    def __init__(self):
        self.bot_logger = setup_logging()
        self.trade_metrics = TradeMetrics()
        self.bybit_client: Optional[BybitContractAPI] = None

        # --- Bot State Variables ---
        self.position_open: bool = False
        self.current_position_side: Optional[str] = None # 'Buy' or 'Sell'
        self.current_position_size: float = 0.0
        self.current_entry_price: float = 0.0 # Entry price from exchange position data
        self.entry_price_for_trade_metrics: float = 0.0 # Price used for PnL calculation in TradeMetrics
        self.entry_fee_for_trade_metrics: float = 0.0
        self.current_price: float = 0.0 # Latest market price
        self.klines_df: Optional[pd.DataFrame] = None

    async def _handle_position_update(self, message: Dict[str, Any]):
        """
        Asynchronous handler for WebSocket position updates.
        This is the single source of truth for the bot's open position state.
        """
        if message.get("topic") == "position" and message.get("data"):
            pos_data = message["data"]
            if pos_data and pos_data[0]:
                pos = pos_data[0]
                symbol = pos.get('symbol')
                size = float(pos.get('size', 0))
                side = pos.get('side')
                avg_price = float(pos.get('avgPrice', 0))
                unrealized_pnl = float(pos.get('unrealisedPnl', 0))

                if size > 0: # Position is open
                    if not self.position_open:
                        self.bot_logger.info(f"{PYRMETHUS_GREEN}🎉 Position detected and tracked via WebSocket for {symbol}.{COLOR_RESET}")
                        # Capture entry details when position just opened
                        self.entry_price_for_trade_metrics = avg_price
                        # Assuming taker fee for entry
                        self.entry_fee_for_trade_metrics = self.trade_metrics.calculate_fee(size, avg_price, is_maker=False)

                    self.position_open = True
                    self.current_position_side = side
                    self.current_position_size = size
                    self.current_entry_price = avg_price
                    self.bot_logger.info(
                        f"{PYRMETHUS_BLUE}💼 Open Position (WS): {self.current_position_side} {self.current_position_size:.4f} {symbol} "
                        f"at {self.current_entry_price:.4f}. Unrealized PnL: {unrealized_pnl:.4f}{COLOR_RESET}"
                    )
                else: # Position is closed (size is 0)
                    if self.position_open: # Only log and record if position was previously open
                        self.bot_logger.info(f"{PYRMETHUS_GREEN}🎉 Position for {symbol} closed successfully via WebSocket!{COLOR_RESET}")
                        exit_price = self.current_price # Use the latest known market price
                        exit_fee = self.trade_metrics.calculate_fee(self.current_position_size, exit_price, is_maker=False)
                        self.trade_metrics.record_trade(
                            self.entry_price_for_trade_metrics, exit_price,
                            self.current_position_size, self.current_position_side,
                            self.entry_fee_for_trade_metrics, exit_fee, asyncio.get_event_loop().time()
                        )
                        log_metrics(self.bot_logger, "Overall Trade Statistics", self.trade_metrics.get_trade_statistics())
                        # Reset trade metrics specific entry data
                        self.entry_price_for_trade_metrics = 0.0
                        self.entry_fee_for_trade_metrics = 0.0

                    # Always reset state variables if size is 0
                    self.position_open = False
                    self.current_position_side = None
                    self.current_position_size = 0.0
                    self.current_entry_price = 0.0
                    self.bot_logger.info(f"{PYRMETHUS_GREY}✅ No open position for {symbol} (WS). Seeking new trade opportunities...{COLOR_RESET}")
            else: # No data or empty data array, implies no open position
                if self.position_open: # Only log and record if position was previously open
                    self.bot_logger.info(f"{PYRMETHUS_GREEN}🎉 Position for {SYMBOL} closed successfully (implied by empty WS data)!{COLOR_RESET}")
                    exit_price = self.current_price
                    exit_fee = self.trade_metrics.calculate_fee(self.current_position_size, exit_price, is_maker=False)
                    self.trade_metrics.record_trade(
                        self.entry_price_for_trade_metrics, exit_price,
                        self.current_position_size, self.current_position_side,
                        self.entry_fee_for_trade_metrics, exit_fee, asyncio.get_event_loop().time()
                    )
                    log_metrics(self.bot_logger, "Overall Trade Statistics", self.trade_metrics.get_trade_statistics())
                    # Reset trade metrics specific entry data
                    self.entry_price_for_trade_metrics = 0.0
                    self.entry_fee_for_trade_metrics = 0.0

                # Always reset state variables if no position data
                self.position_open = False
                self.current_position_side = None
                self.current_position_size = 0.0
                self.current_entry_price = 0.0
                self.bot_logger.info(f"{PYRMETHUS_GREY}✅ No open position for {SYMBOL} (WS). Seeking new trade opportunities...{COLOR_RESET}")
        else:
            self.bot_logger.debug(f"Received non-position WS update: {message}")

    async def _fetch_and_process_klines(self) -> bool:
        """Fetches kline data, processes it, and updates internal DataFrame."""
        try:
            klines_response = await self.bybit_client.get_kline(
                category=BYBIT_CATEGORY, symbol=SYMBOL, interval=INTERVAL, limit=CANDLE_FETCH_LIMIT
            )
            if not klines_response or not klines_response.get('result') or not klines_response['result'].get('list'):
                self.bot_logger.info(f"{COLOR_YELLOW}⚠️ No kline data fetched for {SYMBOL}. Skipping signal generation.{COLOR_RESET}")
                return False

            data = []
            for kline in klines_response['result']['list']:
                timestamp_ms = int(kline[0])
                data.append({
                    'timestamp': pd.to_datetime(timestamp_ms, unit='ms', utc=True),
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5]),
                })
            df = pd.DataFrame(data).set_index('timestamp').sort_index()

            # Ensure we have enough data for indicators
            if len(df) < max(STOCHRSI_K_PERIOD, STOCHRSI_D_PERIOD):
                self.bot_logger.warning(f"{COLOR_YELLOW}Insufficient data for indicators ({len(df)} candles). Need at least {max(STOCHRSI_K_PERIOD, STOCHRSI_D_PERIOD)}.{COLOR_RESET}")
                return False

            self.klines_df = calculate_stochrsi(df, rsi_period=STOCHRSI_K_PERIOD, stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD)
            self.current_price = self.klines_df['close'].iloc[-1]
            return True
        except Exception as e:
            log_exception(self.bot_logger, f"Error fetching or processing klines: {e}", e)
            return False

    def _display_market_info(self, resistance: list, support: list):
        """Prints current market information to the console."""
        if self.klines_df is None:
            self.bot_logger.warning("No klines_df available to display market info.")
            return

        latest_stoch_k = self.klines_df['stoch_k'].iloc[-1] if 'stoch_k' in self.klines_df.columns and not pd.isna(self.klines_df['stoch_k'].iloc[-1]) else "N/A"
        latest_stoch_d = self.klines_df['stoch_d'].iloc[-1] if 'stoch_d' in self.klines_df.columns and not pd.isna(self.klines_df['stoch_d'].iloc[-1]) else "N/A"

        print(f"\n{PYRMETHUS_BLUE}📊 Current Price ({SYMBOL}): {self.current_price:.4f} @ {self.klines_df.index[-1].strftime('%Y-%m-%d %H:%M:%S')}{COLOR_RESET}")
        stoch_k_str = f"{latest_stoch_k:.2f}" if isinstance(latest_stoch_k, float) else str(latest_stoch_k)
        stoch_d_str = f"{latest_stoch_d:.2f}" if isinstance(latest_stoch_d, float) else str(latest_stoch_d)
        print(f"{PYRMETHUS_BLUE}📈 StochRSI K: {stoch_k_str}, D: {stoch_d_str}{COLOR_RESET}")

        if resistance:
            print(f"{COLOR_CYAN}Resistance Levels Detected:{COLOR_RESET}")
            for r_level in resistance:
                print(f"  {COLOR_CYAN}- {r_level['price']:.4f} ({r_level['type']}){COLOR_RESET}")
        if support:
            print(f"{COLOR_MAGENTA}Support Levels Detected:{COLOR_RESET}")
            for s_level in support:
                print(f"  {COLOR_MAGENTA}- {s_level['price']:.4f} ({s_level['type']}){COLOR_RESET}")

    async def _execute_entry(self, signal_type: str, signal_price: float, signal_timestamp: Any, signal_info: Dict[str, Any]):
        """Executes an entry trade based on a signal."""
        self.bot_logger.info(f"{PYRMETHUS_PURPLE}💡 Detected {signal_type.upper()} signal at {signal_price:.4f} (Info: {signal_info.get('stoch_type', 'N/A')}){COLOR_RESET}")

        instrument_info_resp = await self.bybit_client.get_instruments_info(category=BYBIT_CATEGORY, symbol=SYMBOL)
        if not instrument_info_resp or not instrument_info_resp.get('result') or not instrument_info_resp['result'].get('list'):
            self.bot_logger.error(f"{COLOR_RED}Could not fetch instrument info for {SYMBOL}. Cannot place entry order.{COLOR_RESET}")
            return

        instrument_details = instrument_info_resp['result']['list'][0]
        min_qty = float(instrument_details.get('lotSizeFilter', {}).get('minOrderQty', 0))
        qty_step = float(instrument_details.get('lotSizeFilter', {}).get('qtyStep', 0))

        calculated_quantity = calculate_order_quantity(USDT_AMOUNT_PER_TRADE, self.current_price, min_qty, qty_step)
        if calculated_quantity <= 0:
            self.bot_logger.error(f"{COLOR_RED}Calculated entry quantity is zero or negative: {calculated_quantity}. Cannot place order.{COLOR_RESET}")
            return

        calculated_stop_loss_price = None
        calculated_take_profit_price = None

        if STOP_LOSS_PCT is not None:
            if signal_type.upper() == 'BUY':
                calculated_stop_loss_price = self.current_price * (1 - STOP_LOSS_PCT)
            elif signal_type.upper() == 'SELL':
                calculated_stop_loss_price = self.current_price * (1 + STOP_LOSS_PCT)

        if TAKE_PROFIT_PCT is not None:
            if signal_type.upper() == 'BUY':
                calculated_take_profit_price = self.current_price * (1 + TAKE_PROFIT_PCT)
            elif signal_type.upper() == 'SELL':
                calculated_take_profit_price = self.current_price * (1 - TAKE_PROFIT_PCT)

        order_kwargs = {
            "category": BYBIT_CATEGORY,
            "symbol": SYMBOL,
            "side": signal_type.capitalize(),
            "order_type": "Market",
            "qty": calculated_quantity,
        }
        if calculated_stop_loss_price is not None:
            order_kwargs["stopLoss"] = calculated_stop_loss_price
        if calculated_take_profit_price is not None:
            order_kwargs["takeProfit"] = calculated_take_profit_price

        self.bot_logger.info(f"{PYRMETHUS_ORANGE}Attempting to place {signal_type.upper()} order for {calculated_quantity:.4f} {SYMBOL} at market price...{COLOR_RESET}")
        if await self.bybit_client.create_order(**order_kwargs):
            log_trade(self.bot_logger, "Trade executed", {
                "signal_type": signal_type.upper(),
                "price": self.current_price, # Use current_price as the estimated entry price for logging
                "timestamp": str(signal_timestamp),
                "stoch_k": signal_info.get('stoch_k'),
                "stoch_d": signal_info.get('stoch_d'),
                "usdt_amount": USDT_AMOUNT_PER_TRADE,
                "order_type": "Market",
                "stop_loss": f"{calculated_stop_loss_price:.4f}" if calculated_stop_loss_price else "N/A",
                "take_profit": f"{calculated_take_profit_price:.4f}" if calculated_take_profit_price else "N/A",
            })
            # Position state will be updated by WebSocket callback, which then captures exact entry price/fee
            return True
        return False

    async def _execute_exit(self, exit_type: str, exit_price: float, exit_timestamp: Any, exit_info: Dict[str, Any]):
        """Executes an exit trade based on a signal."""
        self.bot_logger.info(f"{PYRMETHUS_PURPLE}💡 Detected {exit_type.upper()} exit signal at {exit_price:.4f} (Info: {exit_info.get('stoch_type', 'N/A')}){COLOR_RESET}")

        if self.current_position_size <= 0:
            self.bot_logger.warning(f"{COLOR_YELLOW}Attempted to exit, but current_position_size is 0. Skipping exit order.{COLOR_RESET}")
            return False

        exit_order_kwargs = {
            "category": BYBIT_CATEGORY,
            "symbol": SYMBOL,
            "side": exit_type.capitalize(), # 'Buy' to close 'Sell', 'Sell' to close 'Buy'
            "order_type": "Market",
            "qty": self.current_position_size,
        }

        self.bot_logger.info(f"{PYRMETHUS_ORANGE}Attempting to place {exit_type.upper()} exit order for {self.current_position_size:.4f} {SYMBOL} at market price...{COLOR_RESET}")
        if await self.bybit_client.create_order(**exit_order_kwargs):
            log_trade(self.bot_logger, "Exit trade executed", {
                "exit_type": exit_type.upper(),
                "price": self.current_price, # Use current_price as the estimated exit price for logging
                "timestamp": str(exit_timestamp),
                "stoch_k": exit_info.get('stoch_k'),
                "stoch_d": exit_info.get('stoch_d'),
                "exit_quantity": self.current_position_size,
                "order_type": "Market"
            })
            # Position state will be updated by WebSocket callback
            return True
        return False

    async def run(self):
        """Main execution loop for the trading bot."""
        self.bot_logger.info("Starting Pyrmethus's Ultra Scalper Bot.")

        print(f"{PYRMETHUS_PURPLE}{COLOR_BOLD}\n🚀 Pyrmethus's Ultra Scalper Bot - Awakened{COLOR_RESET}")
        print(f"{PYRMETHUS_PURPLE}{COLOR_BOLD}=========================================={COLOR_RESET}")
        print(f"{PYRMETHUS_ORANGE}\n⚡ Initializing scalping engine and calibrating sensors...{COLOR_RESET}")

        self.bybit_client = BybitContractAPI(
            api_key=os.getenv("BYBIT_API_KEY"),
            api_secret=os.getenv("BYBIT_API_SECRET"),
            testnet="testnet" in BYBIT_API_ENDPOINT
        )
        self.bot_logger.info("BybitContractAPI initialized.")

        # Start the WebSocket listener in a background task
        listener_task = await self.bybit_client.start_websocket_listener(self._handle_position_update)

        # Subscribe to private topics
        await self.bybit_client.subscribe_ws_private_topic("position")
        # await self.bybit_client.subscribe_ws_private_topic("order") # Uncomment if you need order updates

        # Initial check for open positions using REST, in case WS update is delayed
        initial_pos_response = await self.bybit_client.get_positions(category=BYBIT_CATEGORY, symbol=SYMBOL)
        if initial_pos_response and initial_pos_response.get('result') and initial_pos_response['result'].get('list'):
            simulated_message = {"topic": "position", "data": initial_pos_response['result']['list']}
            await self._handle_position_update(simulated_message)
        else:
            await self._handle_position_update({"topic": "position", "data": []}) # Ensure initial state is no position

        async with self.bybit_client: # Use async with for proper connection management
            while True:
                try:
                    # --- Fetch Latest Market Data ---
                    if not await self._fetch_and_process_klines():
                        await asyncio.sleep(POLLING_INTERVAL_SECONDS)
                        continue # Skip current cycle if kline data is bad

                    # --- Indicator Calculation & Signal Generation ---
                    resistance, support = calculate_fibonacci_pivot_points(self.klines_df)
                    signals = generate_signals(self.klines_df, resistance, support,
                                               stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD,
                                               overbought=STOCHRSI_OVERBOUGHT_LEVEL, oversold=STOCHRSI_OVERSOLD_LEVEL,
                                               use_crossover=USE_STOCHRSI_CROSSOVER)

                    # --- Display Current Market Info ---
                    self._display_market_info(resistance, support)

                    # --- Trade Execution Logic ---
                    if not self.position_open:
                        for signal in signals:
                            signal_type, signal_price, signal_timestamp, signal_info = signal
                            if await self._execute_entry(signal_type, signal_price, signal_timestamp, signal_info):
                                break # Execute only one trade per cycle to avoid multiple simultaneous entries
                    else:
                        self.bot_logger.info(f"{PYRMETHUS_BLUE}🚫 Position already open: {self.current_position_side} {SYMBOL}. Checking for exit signals...{COLOR_RESET}")
                        exit_signals = generate_exit_signals(self.klines_df, self.current_position_side,
                                                             stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD,
                                                             overbought=STOCHRSI_OVERBOUGHT_LEVEL, oversold=STOCHRSI_OVERSOLD_LEVEL,
                                                             use_crossover=USE_STOCHRSI_CROSSOVER)

                        if exit_signals:
                            for exit_signal in exit_signals:
                                exit_type, exit_price, exit_timestamp, exit_info = exit_signal
                                if await self._execute_exit(exit_type, exit_price, exit_timestamp, exit_info):
                                    break # Execute only one exit trade per cycle
                        else:
                            self.bot_logger.info(f"{PYRMETHUS_GREY}No exit signals detected for {self.current_position_side} position.{COLOR_RESET}")

                    # --- Polling Interval ---
                    self.bot_logger.info(f"{PYRMETHUS_ORANGE}Sleeping for {POLLING_INTERVAL_SECONDS} seconds...{COLOR_RESET}")
                    await asyncio.sleep(POLLING_INTERVAL_SECONDS)

                except KeyboardInterrupt:
                    log_exception(self.bot_logger, "Bot stopped by user (KeyboardInterrupt).", None)
                    break # Exit the loop cleanly
                except Exception as e:
                    log_exception(self.bot_logger, f"Critical error in main loop: {str(e)}", e)
                    self.bot_logger.info(f"{COLOR_YELLOW}🔄 Recovering and restarting main loop after 10 seconds...{COLOR_RESET}")
                    await asyncio.sleep(10) # Pause before retrying the loop to prevent rapid error cycling

async def main():
    """Entry point for the Pyrmethus Bot."""
    bot = PyrmethusBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        # This outer try-except is for catching Ctrl+C if it happens before bot.run() starts or
        # if an unhandled exception propagates out of bot.run() after a KeyboardInterrupt.
        pass # The bot's internal loop handles KeyboardInterrupt for graceful shutdown.
    except Exception as e:
        # Ensure that any unhandled exception from bot.run() is also logged
        setup_logging().critical(f"Unhandled exception in main execution: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())

