

import math
import time
import pandas as pd
import ta
import logging
from colorama import Fore, Style, init
from pybit.unified_trading import HTTP
from config import BotConfig

class SupertrendBot:
    def __init__(self):
        init(autoreset=True) # Initialize colorama
        self.config = BotConfig()
        self._setup_logging()

        # --- Pybit Session ---
        if self.config.TESTNET:
            self.session = HTTP(testnet=True, api_key=self.config.API_KEY, api_secret=self.config.API_SECRET)
        else:
            self.session = HTTP(testnet=False, api_key=self.config.API_KEY, api_secret=self.config.API_SECRET)

        # --- Global Trade State (In-memory, not persistent across restarts) ---
        self.current_trade_state = {
            'position': None,
            'entry_bar_time': None,
            'entry_price': None,
            'initial_sl': None,
            'partial_profit_taken': False,
            'order_id': None
        }

        # Ensure API keys are set
        if not self.config.API_KEY or not self.config.API_SECRET:
            self.logger.critical("BYBIT_API_KEY and BYBIT_API_SECRET environment variables must be set.")
            exit(1)

    def _setup_logging(self):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(ColoredFormatter())
        self.logger.addHandler(console_handler)

        # File Handler
        file_handler = logging.FileHandler("supertrendbot.log")
        file_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s'))
        self.logger.addHandler(file_handler)

class ColoredFormatter(logging.Formatter):
    FORMAT = "[%(asctime)s] [%(levelname)s] %(message)s"

    LOG_COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        log_message = super().format(record)
        return self.LOG_COLORS.get(record.levelno, Fore.WHITE) + log_message + Style.RESET_ALL


    def get_klines(self, symbol, interval, limit=200):
        """Fetches kline data from Bybit."""
        try:
            response = self.session.get_kline(
                category=self.config.CATEGORY,
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            if response and response['retCode'] == 0:
                data = response['result']['list']
                df = pd.DataFrame(data, columns=[
                    'start_time', 'open', 'high', 'low', 'close', 'volume', 'turnover'
                ])
                for col in ['start_time', 'open', 'high', 'low', 'close', 'volume', 'turnover']:
                    df[col] = pd.to_numeric(df[col])
                df = df.set_index('start_time')
                return df.sort_index()
            self.logger.error(f"Error fetching klines for {symbol}, {interval}: {response}")
            return None
        except Exception as e:
            self.logger.error(f"Exception fetching klines: {e}")
            return None

    def calculate_indicators(self, df):
        """Calculates technical indicators for a given DataFrame."""
        if df is None or df.empty:
            return None

        df['ema_short'] = ta.trend.ema_indicator(df['close'], window=self.config.EMA_SHORT_PERIOD)
        df['ema_long'] = ta.trend.ema_indicator(df['close'], window=self.config.EMA_LONG_PERIOD)

        df['supertrend_line'], df['supertrend_direction'] = ta.trend.supertrend(
            df['high'], df['low'], df['close'],
            window=self.config.SUPER_TREND_PERIOD,
            fillna=False,
            factor=self.config.SUPER_TREND_MULTIPLIER
        )

        df['volume_ma'] = ta.volume.volume_sma(df['volume'], window=self.config.VOLUME_MA_PERIOD)
        df['rsi'] = ta.momentum.rsi(df['close'], window=self.config.RSI_PERIOD)
        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=self.config.ATR_PERIOD)

        return df

    def get_account_balance(self, coin="USDT"):
        """Retrieves the available balance for a specified coin."""
        try:
            response = self.session.get_wallet_balance(accountType="UNIFIED", coin=coin)
            if response and response['retCode'] == 0:
                for item in response['result']['list']:
                    for c in item['coin']:
                        if c['coin'] == coin:
                            return float(c['availableToWithdraw'])
                return 0.0
            self.logger.error(f"Error getting account balance: {response}")
            return 0.0
        except Exception as e:
            self.logger.error(f"Exception getting account balance: {e}")
            return 0.0

    def get_current_price(self, symbol):
        """Fetches the last traded price for a symbol."""
        try:
            response = self.session.get_tickers(category=self.config.CATEGORY, symbol=symbol)
            if response and response['retCode'] == 0:
                return float(response['result']['list'][0]['lastPrice'])
            self.logger.error(f"Error getting current price for {symbol}: {response}")
            return None
        except Exception as e:
            self.logger.error(f"Exception getting current price: {e}")
            return None

    def place_order(self, symbol, side, qty, order_type="Market", stop_loss=None, take_profit=None):
        """Places a market order with optional Stop Loss and Take Profit."""
        try:
            params = {
                "category": self.config.CATEGORY,
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
                "isLeverage": 0,
            }
            if stop_loss is not None:
                params["stopLoss"] = str(round(stop_loss, 2))
            if take_profit is not None:
                params["takeProfit"] = str(round(take_profit, 2))

            response = self.session.place_order(**params)

            if response and response['retCode'] == 0:
                self.logger.info(f"Order placed successfully: {response['result']}")
                return response['result']['orderId']
            self.logger.error(f"Error placing order: {response}")
            return None
        except Exception as e:
            self.logger.error(f"Exception placing order: {e}")
            return None

    def close_position(self, symbol, side, qty):
        """Closes a portion or all of an open position by placing an opposite market order."""
        opposite_side = "Sell" if side == "Buy" else "Buy"
        self.logger.info(f"Closing {qty:.3f} units of {symbol} with a {opposite_side} market order.")
        return self.place_order(symbol, opposite_side, qty, order_type="Market")

    def get_open_positions(self, symbol):
        """Retrieves details of an open position for a given symbol."""
        try:
            response = self.session.get_positions(category=self.config.CATEGORY, symbol=symbol)
            if response and response['retCode'] == 0:
                positions = response['result']['list']
                if positions:
                    pos = positions[0]
                    if float(pos['size']) > 0:
                        return {
                            'symbol': pos['symbol'],
                            'side': pos['side'],
                            'size': float(pos['size']),
                            'entry_price': float(pos['avgPrice']),
                            'stop_loss': float(pos['stopLoss']) if pos.get('stopLoss') else None,
                            'take_profit': float(pos['takeProfit']) if pos.get('takeProfit') else None,
                            'position_value': float(pos['positionValue'])
                        }
                return None
            self.logger.error(f"Error getting open positions: {response}")
            return None
        except Exception as e:
            self.logger.error(f"Exception getting open positions: {e}")
            return None

    def amend_stop_loss_take_profit(self, symbol, order_id, stop_loss=None, take_profit=None):
        """Amends the Stop Loss or Take Profit of an existing order."""
        if not order_id:
            self.logger.warning("Cannot amend SL/TP: order_id is missing.")
            return False
        try:
            params = {
                "category": self.config.CATEGORY,
                "symbol": symbol,
                "orderId": order_id,
            }
            if stop_loss is not None:
                params["stopLoss"] = str(round(stop_loss, 2))
            if take_profit is not None:
                params["takeProfit"] = str(round(take_profit, 2))

            response = self.session.amend_order(**params)

            if response and response['retCode'] == 0:
                self.logger.info(f"SL/TP amended successfully for order {order_id}: {response['result']}")
                return True
            self.logger.error(f"Error amending SL/TP for order {order_id}: {response}")
            return False
        except Exception as e:
            self.logger.error(f"Exception amending SL/TP: {e}")

    def run(self):
        """Main function to run the trading bot."""
        self.log_message("Starting Supertrend Bot...")

        while True:
            self.log_message("Fetching market data...")
            df_1m = self.get_klines(self.config.SYMBOL, self.config.TF_1M, limit=200)
            df_15m = self.get_klines(self.config.SYMBOL, self.config.TF_15M, limit=200)

            if df_1m is None or df_15m is None or df_1m.empty or df_15m.empty:
                self.log_message("Failed to get klines or klines are empty. Retrying in 60 seconds.", "WARNING")
                time.sleep(60)
                continue

            df_1m = self.calculate_indicators(df_1m)
            df_15m = self.calculate_indicators(df_15m)

            required_1m_data = max(self.config.EMA_LONG_PERIOD, self.config.VOLUME_MA_PERIOD, self.config.RSI_PERIOD, self.config.ATR_PERIOD) + 2
            required_15m_data = max(self.config.EMA_LONG_PERIOD, self.config.SUPER_TREND_PERIOD) + 2

            if df_1m is None or df_15m is None or \
               len(df_1m) < required_1m_data or \
               len(df_15m) < required_15m_data:
                self.log_message(f"Not enough data to calculate all indicators. Need at least {required_1m_data} (1m) and {required_15m_data} (15m) candles. Retrying in 60 seconds.", "WARNING")
                time.sleep(60)
                continue

            last_1m_candle = df_1m.iloc[-1]
            prev_1m_candle = df_1m.iloc[-2]
            last_15m_candle = df_15m.iloc[-1]
            prev_15m_candle = df_15m.iloc[-2]

            current_price = self.get_current_price(self.config.SYMBOL)
            if current_price is None:
                self.log_message("Failed to get current price. Retrying in 60 seconds.", "WARNING")
                time.sleep(60)
                continue

            self.log_message(f"Current Price: {current_price:.2f}")

            exchange_position = self.get_open_positions(self.config.SYMBOL)

            if exchange_position and not self.current_trade_state['position']:
                self.log_message("Detected an open position not tracked internally. Attempting to sync.", "WARNING")
                self.current_trade_state['position'] = exchange_position
                self.current_trade_state['entry_price'] = exchange_position['entry_price']
                self.current_trade_state['initial_sl'] = exchange_position['stop_loss']
                self.current_trade_state['partial_profit_taken'] = False
                self.current_trade_state['order_id'] = None
                self.log_message("WARNING: For untracked positions, dynamic SL/TP adjustments will NOT work as order_id is unknown.", "WARNING")
                self.current_trade_state['entry_bar_time'] = last_1m_candle.name

            elif not exchange_position and self.current_trade_state['position']:
                self.log_message("Detected that position was closed on exchange. Clearing internal state.", "INFO")
                self.current_trade_state = {
                    'position': None, 'entry_bar_time': None, 'entry_price': None,
                    'initial_sl': None, 'partial_profit_taken': False, 'order_id': None
                }
            elif exchange_position:
                self.current_trade_state['position'] = exchange_position


            if self.current_trade_state['position']:
                pos = self.current_trade_state['position']
                self.log_message(f"Open position found: {pos['side']} {pos['size']:.3f} at {pos['entry_price']:.2f}")

                current_atr = df_1m['atr'].iloc[-1]
                if pd.isna(current_atr) or current_atr == 0:
                    self.log_message("ATR is not available or zero for position management. Skipping ATR-based dynamic SL/TP.", "WARNING")
                    current_atr = 0.00000001

                if self.current_trade_state['entry_bar_time']:
                    bars_in_trade = (last_1m_candle.name - self.current_trade_state['entry_bar_time']) / (60 * 1000)
                    self.log_message(f"Bars in trade: {bars_in_trade:.0f}")

                                    if bars_in_trade >= self.config.MAX_TRADE_DURATION_BARS:
                                        self.log_message(f"Max trade duration ({self.config.MAX_TRADE_DURATION_BARS} bars) reached. Closing position.", "INFO")
                                        self.close_position(self.config.SYMBOL, pos['side'], pos['size'])
                                        self.current_trade_state = {
                                            'position': None, 'entry_bar_time': None, 'entry_price': None,
                                            'initial_sl': None, 'partial_profit_taken': False, 'order_id': None
                                        }                        time.sleep(5)
                        continue

                if self.current_trade_state['order_id']:
                    if not self.current_trade_state['partial_profit_taken']:
                        profit_target_price = self.current_trade_state['entry_price'] + (current_atr * self.config.PARTIAL_PROFIT_ATR_MULTIPLIER) if pos['side'] == "Buy" else \
                                              self.current_trade_state['entry_price'] - (current_atr * self.config.PARTIAL_PROFIT_ATR_MULTIPLIER)

                        if (pos['side'] == "Buy" and current_price >= profit_target_price) or \
                           (pos['side'] == "Sell" and current_price <= profit_target_price):

                            qty_to_close = pos['size'] * self.config.PARTIAL_PROFIT_PERCENT
                            if qty_to_close >= 0.001:
                                self.log_message(f"Taking partial profit ({self.config.PARTIAL_PROFIT_PERCENT*100}%) on {pos['side']} position. Closing {qty_to_close:.3f} units.", "INFO")
                                self.close_position(self.config.SYMBOL, pos['side'], qty_to_close)
                                self.current_trade_state['partial_profit_taken'] = True

                                new_sl_after_partial = self.current_trade_state['entry_price']

                                if (pos['side'] == "Buy" and (pos['stop_loss'] is None or new_sl_after_partial > pos['stop_loss'])) or \
                                   (pos['side'] == "Sell" and (pos['stop_loss'] is None or new_sl_after_partial < pos['stop_loss'])):
                                    self.log_message(f"Amending SL to {new_sl_after_partial:.2f} (from {pos['stop_loss']:.2f}) after partial profit.", "INFO")
                                    self.amend_stop_loss_take_profit(self.SYMBOL, self.current_trade_state['order_id'], stop_loss=new_sl_after_partial)
                                    time.sleep(5)
                            else:
                                self.log_message(f"Calculated partial profit quantity ({qty_to_close:.3f}) is too small. Skipping partial profit.", "WARNING")


                    if self.current_trade_state['entry_price'] and self.current_trade_state['initial_sl'] and \
                       not self.current_trade_state['partial_profit_taken'] and \
                       (pos['stop_loss'] == self.current_trade_state['initial_sl'] or pos['stop_loss'] is None):

                        profit_in_atr = ((current_price - self.current_trade_state['entry_price']) / current_atr) if pos['side'] == "Buy" else \
                                        ((self.current_trade_state['entry_price'] - current_price) / current_atr)

                        if profit_in_atr >= self.config.BREAK_EVEN_PROFIT_ATR:
                            self.log_message(f"Profit of {profit_in_atr:.2f} ATR reached. Moving stop loss to break-even.", "INFO")
                            new_sl_breakeven = self.current_trade_state['entry_price']

                            if (pos['side'] == "Buy" and (pos['stop_loss'] is None or new_sl_breakeven > pos['stop_loss'])) or \
                               (pos['side'] == "Sell" and (pos['stop_loss'] is None or new_sl_breakeven < pos['stop_loss'])):
                                self.log_message(f"Amending SL to {new_sl_breakeven:.2f} (from {pos['stop_loss']:.2f}) due to break-even activation.", "INFO")
                                self.amend_stop_loss_take_profit(self.SYMBOL, self.current_trade_state['order_id'], stop_loss=new_sl_breakeven)
                                time.sleep(5)

                    if self.current_trade_state['partial_profit_taken'] or \
                       (self.current_trade_state['entry_bar_time'] and \
                        (last_1m_candle.name - self.current_trade_state['entry_bar_time']) / (60 * 1000) >= self.config.TRAILING_STOP_ACTIVATION_BARS and \
                        ((pos['side'] == "Buy" and current_price > self.current_trade_state['entry_price']) or \
                         (pos['side'] == "Sell" and current_price < self.current_trade_state['entry_price']))):

                        if pos['side'] == "Buy":
                            new_trailing_sl = current_price - (current_atr * self.config.TRAILING_STOP_ATR_MULTIPLIER)
                        else:
                            new_trailing_sl = current_price + (current_atr * self.config.TRAILING_STOP_ATR_MULTIPLIER)

                        if (pos['side'] == "Buy" and (pos['stop_loss'] is None or new_trailing_sl > pos['stop_loss'])) or \
                           (pos['side'] == "Sell" and (pos['stop_loss'] is None or new_trailing_sl < pos['stop_loss'])):
                            self.log_message(f"Amending SL to {new_trailing_sl:.2f} (from {pos['stop_loss']:.2f}) due to trailing stop.", "INFO")
                            self.amend_stop_loss_take_profit(self.SYMBOL, self.current_trade_state['order_id'], stop_loss=new_trailing_sl)
                            time.sleep(5)
                else:
                    self.log_message("WARNING: order_id is missing for the current position. Dynamic SL/TP adjustments are disabled.", "WARNING")


            else:
                self.log_message("No open position. Looking for trade opportunities.")

                is_15m_uptrend = (df_15m['supertrend_direction'].iloc[-1] == 1)
                is_15m_downtrend = (df_15m['supertrend_direction'].iloc[-1] == 0)

                is_15m_ema_bullish_sloped = (df_15m['ema_short'].iloc[-1] > df_15m['ema_long'].iloc[-1] and
                                              df_15m['ema_short'].iloc[-1] > prev_15m_candle['ema_short'] and
                                              df_15m['ema_long'].iloc[-1] > prev_15m_candle['ema_long'])
                is_15m_ema_bearish_sloped = (df_15m['ema_short'].iloc[-1] < df_15m['ema_long'].iloc[-1] and
                                              df_15m['ema_short'].iloc[-1] < prev_15m_candle['ema_short'] and
                                              df_15m['ema_long'].iloc[-1] < prev_15m_candle['ema_long'])

                is_1m_price_at_ema9_long = (prev_1m_candle['close'] < prev_1m_candle['ema_short'] and last_1m_candle['close'] >= last_1m_candle['ema_short'])
                is_1m_price_at_ema9_short = (prev_1m_candle['close'] > prev_1m_candle['ema_short'] and last_1m_candle['close'] <= last_1m_candle['ema_short'])

                is_volume_spike = (last_1m_candle['volume'] > self.config.VOLUME_SPIKE_MULTIPLIER * last_1m_candle['volume_ma'])

                is_rsi_bullish = (last_1m_candle['rsi'] > self.config.RSI_CONFIRMATION_LEVEL and last_1m_candle['rsi'] > prev_1m_candle['rsi'])
                is_rsi_bearish = (last_1m_candle['rsi'] < self.config.RSI_CONFIRMATION_LEVEL and last_1m_candle['rsi'] < prev_1m_candle['rsi'])


                long_conditions = (
                    is_15m_uptrend and is_15m_ema_bullish_sloped and
                    is_1m_price_at_ema9_long and
                    is_volume_spike and
                    is_rsi_bullish
                )

                short_conditions = (
                    is_15m_downtrend and is_15m_ema_bearish_sloped and
                    is_1m_price_at_ema9_short and
                    is_volume_spike and
                    is_rsi_bearish
                )

                side = None
                if long_conditions:
                    side = "Buy"
                    self.log_message("Long entry conditions met.", "INFO")
                elif short_conditions:
                    side = "Sell"
                    self.log_message("Short entry conditions met.", "INFO")

                if side:
                    account_balance = self.get_account_balance()
                    if account_balance == 0:
                        self.log_message("Could not get account balance. Cannot place trade.", "ERROR")
                        time.sleep(60)
                        continue

                    current_atr = df_1m['atr'].iloc[-1]
                    if pd.isna(current_atr) or current_atr == 0:
                        self.log_message("ATR is not available or zero. Cannot place trade.", "ERROR")
                        time.sleep(60)
                        continue

                    if side == "Buy":
                        stop_loss_price = current_price - (current_atr * self.config.STOP_LOSS_ATR_MULTIPLIER)
                        take_profit_price = current_price + (current_atr * self.config.TAKE_PROFIT_ATR_MULTIPLIER)
                    else:
                        stop_loss_price = current_price + (current_atr * self.config.STOP_LOSS_ATR_MULTIPLIER)
                        take_profit_price = current_price - (current_atr * self.config.TAKE_PROFIT_ATR_MULTIPLIER)

                    risk_amount = account_balance * (self.config.RISK_PER_TRADE_PERCENT / 100)
                    price_diff = abs(current_price - stop_loss_price)
                    if price_diff == 0:
                        self.log_message("Stop loss price is too close to entry price (price_diff is zero). Cannot place trade.", "ERROR")
                        time.sleep(60)
                        continue

                    qty = risk_amount / price_diff
                    qty = math.floor(qty * 1000) / 1000

                    if qty <= 0.001:
                        self.log_message(f"Calculated quantity ({qty:.3f}) is zero or too small. Cannot place trade.", "WARNING")
                        time.sleep(60)
                        continue

                    self.log_message(f"Attempting to place {side} order for {qty:.3f} {self.config.SYMBOL} at {current_price:.2f}. SL: {stop_loss_price:.2f}, TP: {take_profit_price:.2f}", "INFO")

                    order_id = self.place_order(self.config.SYMBOL, side, qty, stop_loss=stop_loss_price, take_profit=take_profit_price)

                    if order_id:
                        self.log_message(f"Trade entered successfully. Order ID: {order_id}", "SUCCESS")
                        self.current_trade_state['position'] = {
                            'symbol': self.SYMBOL, 'side': side, 'size': qty,
                            'entry_price': current_price, 'stop_loss': stop_loss_price,
                            'take_profit': take_profit_price
                        }
                        self.current_trade_state['entry_bar_time'] = last_1m_candle.name
                        self.current_trade_state['entry_price'] = current_price
                        self.current_trade_state['initial_sl'] = stop_loss_price
                        self.current_trade_state['partial_profit_taken'] = False
                        self.current_trade_state['order_id'] = order_id
                    else:
                        self.log_message("Failed to place trade.", "ERROR")

            self.log_message("Waiting for next candle...", "INFO")
            time.sleep(60)

if __name__ == "__main__":
    bot = SupertrendBot()
    bot.run()
