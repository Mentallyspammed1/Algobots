# PSG.py - Pyrmethus's Ultra Scalper Bot (Upgraded)
import os
import asyncio
import pandas as pd
import logging
from typing import Any, Dict, List, Tuple, Union, Optional, Callable
from dotenv import load_dotenv
from decimal import Decimal, getcontext

# --- Set Decimal Precision ---
getcontext().prec = 38

# --- Pyrmethus's Color Codex ---
from color_codex import (
    COLOR_RESET, COLOR_BOLD, COLOR_DIM,
    COLOR_RED, COLOR_GREEN, COLOR_YELLOW, COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN,
    PYRMETHUS_GREEN, PYRMETHUS_BLUE, PYRMETHUS_PURPLE, PYRMETHUS_ORANGE, PYRMETHUS_GREY
)

# --- Import Configuration and Indicator Logic ---
from config import (
    SYMBOL, INTERVAL, USDT_AMOUNT_PER_TRADE, PIVOT_LEFT_BARS, PIVOT_RIGHT_BARS, PIVOT_TOLERANCE_PCT,
    STOCHRSI_K_PERIOD, STOCHRSI_D_PERIOD, STOCHRSI_OVERBOUGHT_LEVEL,
    STOCHRSI_OVERSOLD_LEVEL, USE_STOCHRSI_CROSSOVER, STOP_LOSS_PCT,
    TAKE_PROFIT_PCT, BYBIT_API_ENDPOINT, BYBIT_CATEGORY, CANDLE_FETCH_LIMIT,
    POLLING_INTERVAL_SECONDS, API_REQUEST_RETRIES, API_BACKOFF_FACTOR
)
from indicators import calculate_fibonacci_pivot_points, calculate_stochrsi, calculate_atr
from strategy import generate_signals, generate_exit_signals
from bybit_api import BybitContractAPI
from bot_ui import display_market_info

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

        # --- Bot State Variables (using Decimal for precision) ---
        self.inventory: Decimal = Decimal('0') # Primary position tracker. >0 for long, <0 for short.
        self.entry_price: Decimal = Decimal('0')
        self.unrealized_pnl: Decimal = Decimal('0')
        
        # Legacy state variables, to be harmonized or deprecated
        self.position_open: bool = False
        self.current_position_side: Optional[str] = None # 'Buy' or 'Sell'
        
        # Trade-specific metrics
        self.entry_price_for_trade_metrics: Decimal = Decimal('0')
        self.entry_fee_for_trade_metrics: Decimal = Decimal('0')
        
        self.current_price: Decimal = Decimal('0')
        self.klines_df: Optional[pd.DataFrame] = None
        self.cached_atr: Optional[Decimal] = None

    async def _handle_position_update(self, message: Dict[str, Any]):
        """
        Asynchronous handler for WebSocket position updates.
        This is the single source of truth for the bot's open position state.
        """
        if message.get("topic") != "position" or not message.get("data"):
            self.bot_logger.debug(f"Received non-position or empty WS update: {message}")
            return

        pos_data = message["data"]
        if not pos_data or not pos_data[0]: # No open position
            if self.inventory != Decimal('0'):
                self.bot_logger.info(f"{PYRMETHUS_GREEN}🎉 Position for {SYMBOL} closed successfully (inferred from empty WS data)!{COLOR_RESET}")
                exit_price = self.current_price
                exit_fee = self.trade_metrics.calculate_fee(abs(self.inventory), exit_price, is_maker=False)
                self.trade_metrics.record_trade(
                    self.entry_price_for_trade_metrics, exit_price,
                    abs(self.inventory), self.current_position_side,
                    self.entry_fee_for_trade_metrics, exit_fee, asyncio.get_event_loop().time()
                )
                log_metrics(self.bot_logger, "Overall Trade Statistics", self.trade_metrics.get_trade_statistics())
            
            # Reset all position state variables
            self.inventory = Decimal('0')
            self.entry_price = Decimal('0')
            self.unrealized_pnl = Decimal('0')
            self.position_open = False
            self.current_position_side = None
            self.entry_price_for_trade_metrics = Decimal('0')
            self.entry_fee_for_trade_metrics = Decimal('0')
            self.bot_logger.info(f"{PYRMETHUS_GREY}✅ No open position for {SYMBOL} (WS). Seeking new trade opportunities...{COLOR_RESET}")
            return

        # Position is open
        pos = pos_data[0]
        symbol = pos.get('symbol')
        size_str = pos.get('size', '0')
        side = pos.get('side')
        avg_price_str = pos.get('avgPrice', '0')
        unrealized_pnl_str = pos.get('unrealisedPnl', '0')

        new_size = Decimal(size_str)
        new_entry_price = Decimal(avg_price_str)
        
        # Determine signed inventory
        signed_inventory = new_size if side == 'Buy' else -new_size
        
        position_changed = self.inventory != signed_inventory
        entry_price_changed = self.entry_price != new_entry_price and new_size > 0

        if not self.position_open and new_size > 0: # Position just opened
            self.bot_logger.info(f"{PYRMETHUS_GREEN}🎉 Position detected and tracked via WebSocket for {symbol}.{COLOR_RESET}")
            self.entry_price_for_trade_metrics = new_entry_price
            self.entry_fee_for_trade_metrics = self.trade_metrics.calculate_fee(new_size, new_entry_price, is_maker=False)

        # Update state
        self.inventory = signed_inventory
        self.entry_price = new_entry_price
        self.unrealized_pnl = Decimal(unrealized_pnl_str) if unrealized_pnl_str else Decimal('0')
        self.position_open = new_size > 0
        self.current_position_side = side if new_size > 0 else None

        if self.position_open:
            self.bot_logger.info(
                f"{PYRMETHUS_BLUE}💼 Open Position (WS): {self.current_position_side} {abs(self.inventory):.4f} {symbol} "
                f"at {self.entry_price:.4f}. Unrealized PnL: {self.unrealized_pnl:.4f}{COLOR_RESET}"
            )
            # If position details changed, update TP/SL
            if position_changed or entry_price_changed:
                await self._update_take_profit_stop_loss()
        else:
            # This case is handled by the "No open position" block at the start
            pass

    async def _update_take_profit_stop_loss(self):
        """Sets or updates Take Profit and Stop Loss for the current position."""
        if not self.position_open or self.inventory == Decimal('0'):
            self.bot_logger.debug(f"[{SYMBOL}] No open position to set TP/SL for.")
            return

        if STOP_LOSS_PCT is None and TAKE_PROFIT_PCT is None:
            self.bot_logger.debug(f"[{SYMBOL}] No TP or SL percentage configured. Skipping.")
            return

        take_profit_price = None
        stop_loss_price = None

        if self.inventory > 0: # Long position
            if TAKE_PROFIT_PCT is not None:
                take_profit_price = self.entry_price * (Decimal('1') + Decimal(str(TAKE_PROFIT_PCT)))
            if STOP_LOSS_PCT is not None:
                stop_loss_price = self.entry_price * (Decimal('1') - Decimal(str(STOP_LOSS_PCT)))
        elif self.inventory < 0: # Short position
            if TAKE_PROFIT_PCT is not None:
                take_profit_price = self.entry_price * (Decimal('1') - Decimal(str(TAKE_PROFIT_PCT)))
            if STOP_LOSS_PCT is not None:
                stop_loss_price = self.entry_price * (Decimal('1') + Decimal(str(STOP_LOSS_PCT)))

        self.bot_logger.info(f"{PYRMETHUS_ORANGE}Attempting to set TP/SL for {SYMBOL}: TP={take_profit_price}, SL={stop_loss_price}{COLOR_RESET}")
        await self.bybit_client.set_trading_stop(
            category=BYBIT_CATEGORY,
            symbol=SYMBOL,
            take_profit=f"{take_profit_price:.4f}" if take_profit_price else None,
            stop_loss=f"{stop_loss_price:.4f}" if stop_loss_price else None,
            positionIdx=0
        )

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
                data.append({
                    'timestamp': pd.to_datetime(int(kline[0]), unit='ms', utc=True),
                    'open': Decimal(kline[1]),
                    'high': Decimal(kline[2]),
                    'low': Decimal(kline[3]),
                    'close': Decimal(kline[4]),
                    'volume': Decimal(kline[5]),
                })
            df = pd.DataFrame(data).set_index('timestamp').sort_index()

            if len(df) < max(STOCHRSI_K_PERIOD, 14): # 14 for ATR
                self.bot_logger.warning(f"{COLOR_YELLOW}Insufficient data for indicators ({len(df)} candles). Need at least {max(STOCHRSI_K_PERIOD, 14)}.{COLOR_RESET}")
                return False

            self.klines_df = calculate_stochrsi(df.copy(), rsi_period=STOCHRSI_K_PERIOD, stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD)
            self.klines_df['atr'] = calculate_atr(self.klines_df)
            self.cached_atr = self.klines_df['atr'].iloc[-1]
            self.current_price = self.klines_df['close'].iloc[-1]
            return True
        except Exception as e:
            log_exception(self.bot_logger, f"Error fetching or processing klines: {e}", e)
            return False

    async def _execute_entry(self, signal_type: str, signal_price: Decimal, signal_timestamp: Any, signal_info: Dict[str, Any]):
        """Executes an entry trade based on a signal."""
        self.bot_logger.info(f"{PYRMETHUS_PURPLE}💡 Detected {signal_type.upper()} signal at {signal_price:.4f} (Info: {signal_info.get('stoch_type', 'N/A')}){COLOR_RESET}")

        instrument_info_resp = await self.bybit_client.get_instruments_info(category=BYBIT_CATEGORY, symbol=SYMBOL)
        if not instrument_info_resp or not instrument_info_resp.get('result') or not instrument_info_resp['result'].get('list'):
            self.bot_logger.error(f"{COLOR_RED}Could not fetch instrument info for {SYMBOL}. Cannot place entry order.{COLOR_RESET}")
            return

        instrument_details = instrument_info_resp['result']['list'][0]
        min_qty = Decimal(instrument_details.get('lotSizeFilter', {}).get('minOrderQty', '0'))
        qty_step = Decimal(instrument_details.get('lotSizeFilter', {}).get('qtyStep', '0'))

        calculated_quantity = calculate_order_quantity(USDT_AMOUNT_PER_TRADE, self.current_price, min_qty, qty_step)
        if calculated_quantity <= 0:
            self.bot_logger.error(f"{COLOR_RED}Calculated entry quantity is zero or negative: {calculated_quantity}. Cannot place order.{COLOR_RESET}")
            return

        order_kwargs = {
            "category": BYBIT_CATEGORY,
            "symbol": SYMBOL,
            "side": signal_type.capitalize(),
            "order_type": "Market",
            "qty": str(calculated_quantity),
        }

        self.bot_logger.info(f"{PYRMETHUS_ORANGE}Attempting to place {signal_type.upper()} order for {calculated_quantity:.4f} {SYMBOL} at market price...{COLOR_RESET}")
        if await self.bybit_client.create_order(**order_kwargs):
            log_trade(self.bot_logger, "Entry trade executed", {
                "signal_type": signal_type.upper(),
                "price": self.current_price,
                "timestamp": str(signal_timestamp),
                "stoch_k": signal_info.get('stoch_k'),
                "stoch_d": signal_info.get('stoch_d'),
                "usdt_amount": USDT_AMOUNT_PER_TRADE,
                "order_type": "Market",
            })
            # Position state and TP/SL will be updated by WebSocket callback
            return True
        return False

    async def _execute_exit(self, exit_type: str, exit_price: Decimal, exit_timestamp: Any, exit_info: Dict[str, Any]):
        """Executes an exit trade based on a signal."""
        self.bot_logger.info(f"{PYRMETHUS_PURPLE}💡 Detected {exit_type.upper()} exit signal at {exit_price:.4f} (Info: {exit_info.get('stoch_type', 'N/A')}){COLOR_RESET}")

        if abs(self.inventory) <= 0:
            self.bot_logger.warning(f"{COLOR_YELLOW}Attempted to exit, but current inventory is 0. Skipping exit order.{COLOR_RESET}")
            return False

        exit_order_kwargs = {
            "category": BYBIT_CATEGORY,
            "symbol": SYMBOL,
            "side": exit_type.capitalize(),
            "order_type": "Market",
            "qty": str(abs(self.inventory)),
        }

        self.bot_logger.info(f"{PYRMETHUS_ORANGE}Attempting to place {exit_type.upper()} exit order for {abs(self.inventory):.4f} {SYMBOL} at market price...{COLOR_RESET}")
        if await self.bybit_client.create_order(**exit_order_kwargs):
            log_trade(self.bot_logger, "Exit trade executed", {
                "exit_type": exit_type.upper(),
                "price": self.current_price,
                "timestamp": str(exit_timestamp),
                "stoch_k": exit_info.get('stoch_k'),
                "stoch_d": exit_info.get('stoch_d'),
                "exit_quantity": str(abs(self.inventory)),
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
            testnet="testnet" in BYBIT_API_ENDPOINT
        )
        self.bot_logger.info("BybitContractAPI initialized.")

        listener_task = await self.bybit_client.start_websocket_listener(self._handle_position_update)
        await self.bybit_client.subscribe_ws_private_topic("position")

        initial_pos_response = await self.bybit_client.get_positions(category=BYBIT_CATEGORY, symbol=SYMBOL)
        if initial_pos_response and initial_pos_response.get('result') and initial_pos_response['result'].get('list'):
            simulated_message = {"topic": "position", "data": initial_pos_response['result']['list']}
            await self._handle_position_update(simulated_message)
        else:
            await self._handle_position_update({"topic": "position", "data": []})

        async with self.bybit_client:
            while True:
                try:
                    if not await self._fetch_and_process_klines():
                        await asyncio.sleep(POLLING_INTERVAL_SECONDS)
                        continue

                    resistance, support = calculate_fibonacci_pivot_points(self.klines_df)
                    
                    display_market_info(self.klines_df, self.current_price, SYMBOL, resistance, support, self.bot_logger)

                    if not self.position_open:
                        signals = generate_signals(self.klines_df, resistance, support,
                                                   stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD,
                                                   overbought=STOCHRSI_OVERBOUGHT_LEVEL, oversold=STOCHRSI_OVERSOLD_LEVEL,
                                                   use_crossover=USE_STOCHRSI_CROSSOVER)
                        for signal in signals:
                            signal_type, signal_price, signal_timestamp, signal_info = signal
                            if await self._execute_entry(signal_type, signal_price, signal_timestamp, signal_info):
                                break
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
                                    break
                        else:
                            self.bot_logger.info(f"{PYRMETHUS_GREY}No exit signals detected for {self.current_position_side} position.{COLOR_RESET}")

                    self.bot_logger.info(f"{PYRMETHUS_ORANGE}Sleeping for {POLLING_INTERVAL_SECONDS} seconds...{COLOR_RESET}")
                    await asyncio.sleep(POLLING_INTERVAL_SECONDS)

                except KeyboardInterrupt:
                    log_exception(self.bot_logger, "Bot stopped by user (KeyboardInterrupt).", None)
                    break
                except Exception as e:
                    log_exception(self.bot_logger, f"Critical error in main loop: {str(e)}", e)
                    self.bot_logger.info(f"{COLOR_YELLOW}🔄 Recovering and restarting main loop after 10 seconds...{COLOR_RESET}")
                    await asyncio.sleep(10)

async def main():
    """Entry point for the Pyrmethus Bot."""
    load_dotenv()
    bot = PyrmethusBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        setup_logging().critical(f"Unhandled exception in main execution: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())