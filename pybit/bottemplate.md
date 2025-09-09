Using limit and conditional orders in your bot will give you more strategic control over your entries and exits. Here's a version of your bot template that uses separate functions to place these order types, which you can call from your main trading logic.
Place Order Functions
I've added two new functions to the template: place_limit_order and place_conditional_order.
 * place_limit_order: This function is designed for trades you want to make at a specific, fixed price. It sets the orderType to 'Limit' and requires a price parameter.
 * place_conditional_order: This function is for more advanced breakout strategies. It places a "stop-entry" order that is triggered when the market reaches a specified triggerPrice. This order can then be executed as either a market or limit order.
In your main loop, you would call these functions instead of the place_batch_orders function. For example, if your strategy is to buy a breakout above a resistance level, you would set a conditional order with the resistance price as the trigger.
Here is the updated code:
#!/usr/bin/env python3

import pandas as pd
import pandas_ta as ta
import logging
from dotenv import load_dotenv
import os
from pybit.unified_trading import HTTP, WebSocket
from time import sleep
import datetime
import pytz
import json

# --- Setup and Configuration ---
load_dotenv()

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# --- Configuration and API Credentials ---
api = os.getenv("BYBIT_API_KEY")
secret = os.getenv("BYBIT_API_SECRET")

if not api or not secret:
    logging.error("API keys not found. Please check your .env file.")
    exit()

# Config:
atr_tp_multiplier = 2.0
atr_sl_multiplier = 1.5
timeframe = 15
mode = 1
leverage = 10
qty = 50

# Timezone configuration
timezone_str = 'America/New_York'
market_open_hour = 9
market_close_hour = 17

# --- Global State ---
latest_kline_data = {}

# --- WebSocket Handler ---
def handle_message(message):
    """Callback function to handle incoming WebSocket messages."""
    global latest_kline_data
    try:
        data = json.loads(message)
        if 'topic' in data and data['topic'].startswith('kline.'):
            symbol = data['data'][0]['symbol']
            kline_update = data['data'][0]
            latest_kline_data[symbol] = {
                'Time': kline_update['start'],
                'Open': float(kline_update['open']),
                'High': float(kline_update['high']),
                'Low': float(kline_update['low']),
                'Close': float(kline_update['close']),
                'Volume': float(kline_update['volume']),
                'Turnover': float(kline_update['turnover'])
            }
            logging.debug(f"Received WebSocket update for {symbol}")
    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode WebSocket message: {e}")
    except Exception as e:
        logging.error(f"Error in WebSocket handler: {e}")

# --- API Session ---
try:
    session = HTTP(
        api_key=api,
        api_secret=secret
    )
    logging.info("Successfully connected to Bybit API.")
except Exception as e:
    logging.error(f"Failed to connect to Bybit API: {e}")
    exit()

# --- Helper Functions ---
def get_current_time(timezone_str):
    """Returns the current local and UTC time objects."""
    tz = pytz.timezone(timezone_str)
    local_time = datetime.datetime.now(tz)
    utc_time = datetime.datetime.now(pytz.utc)
    return local_time, utc_time

def is_market_open(local_time):
    """Checks if the market is open based on configured hours."""
    current_hour = local_time.hour
    return market_open_hour <= current_hour < market_close_hour

# --- Core Functions ---
def get_balance():
    """Fetches and returns the wallet balance in USDT."""
    try:
        resp = session.get_wallet_balance(accountType="CONTRACT", coin="USDT")['result']['list'][0]['coin'][0]['walletBalance']
        return float(resp)
    except Exception as err:
        logging.error(f"Error getting balance: {err}")
        return None

def get_tickers():
    """Retrieves all USDT perpetual linear symbols from the derivatives market."""
    try:
        resp = session.get_tickers(category="linear")['result']['list']
        symbols = [elem['symbol'] for elem in resp if 'USDT' in elem['symbol'] and not 'USDC' in elem['symbol']]
        return symbols
    except Exception as err:
        logging.error(f"Error getting tickers: {err}")
        return None

def klines(symbol):
    """Fetches klines (candlestick data) for a given symbol and returns a pandas DataFrame."""
    try:
        resp = session.get_kline(
            category='linear',
            symbol=symbol,
            interval=timeframe,
            limit=500
        )['result']['list']
        df = pd.DataFrame(resp, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Turnover'])
        df = df.set_index('Time').astype(float)
        return df[::-1]
    except Exception as err:
        logging.error(f"Error getting klines for {symbol}: {err}")
        return None

def get_orderbook_levels(symbol):
    """Analyzes the order book to find strong support and resistance levels."""
    try:
        resp = session.get_orderbook(
            category='linear',
            symbol=symbol,
            limit=50
        )['result']
        bids = pd.DataFrame(resp['bids'], columns=['price', 'volume']).astype(float)
        asks = pd.DataFrame(resp['asks'], columns=['price', 'volume']).astype(float)
        strong_support_price = bids.loc[bids['volume'].idxmax()]['price']
        strong_resistance_price = asks.loc[asks['volume'].idxmax()]['price']
        return strong_support_price, strong_resistance_price
    except Exception as err:
        logging.error(f"Error getting orderbook for {symbol}: {err}")
        return None, None

def get_positions():
    """Returns a list of symbols with open positions."""
    try:
        resp = session.get_positions(category='linear', settleCoin='USDT')['result']['list']
        return [elem['symbol'] for elem in resp if float(elem['leverage']) > 0]
    except Exception as err:
        logging.error(f"Error getting positions: {err}")
        return []

def set_mode(symbol):
    """Sets the margin mode and leverage for a symbol."""
    try:
        session.switch_margin_mode(
            category='linear',
            symbol=symbol,
            tradeMode=mode,
            buyLeverage=leverage,
            sellLeverage=leverage
        )
        logging.info(f"Margin mode and leverage set for {symbol}.")
    except Exception as err:
        logging.error(f"Error setting mode for {symbol}: {err}")

def get_precisions(symbol):
    """Retrieves the decimal precision for price and quantity."""
    try:
        resp = session.get_instruments_info(
            category='linear',
            symbol=symbol
        )['result']['list'][0]
        price_step = resp['priceFilter']['tickSize']
        qty_step = resp['lotSizeFilter']['qtyStep']
        price_precision = len(price_step.split('.')[1]) if '.' in price_step else 0
        qty_precision = len(qty_step.split('.')[1]) if '.' in qty_step else 0
        return price_precision, qty_precision
    except Exception as err:
        logging.error(f"Error getting precisions for {symbol}: {err}")
        return 0, 0

def place_limit_order(symbol, side, price, qty, tp_price=None, sl_price=None):
    """Places a limit order with optional TP/SL."""
    try:
        params = {
            'category': 'linear',
            'symbol': symbol,
            'side': side,
            'orderType': 'Limit',
            'qty': qty,
            'price': price,
            'timeInForce': 'GTC' # Good-Til-Cancelled
        }
        if tp_price:
            params['takeProfit'] = tp_price
            params['tpTriggerBy'] = 'Market'
        if sl_price:
            params['stopLoss'] = sl_price
            params['slTriggerBy'] = 'Market'
        
        response = session.place_order(**params)
        logging.info(f"Limit order placed for {symbol}: {response}")
    except Exception as err:
        logging.error(f"Error placing limit order for {symbol}: {err}")

def place_conditional_order(symbol, side, qty, trigger_price, order_type='Market', tp_price=None, sl_price=None):
    """Places a conditional order that becomes active at a trigger price."""
    try:
        params = {
            'category': 'linear',
            'symbol': symbol,
            'side': side,
            'orderType': order_type,
            'qty': qty,
            'triggerPrice': trigger_price,
            'triggerBy': 'Market'
        }
        if tp_price:
            params['takeProfit'] = tp_price
            params['tpTriggerBy'] = 'Market'
        if sl_price:
            params['stopLoss'] = sl_price
            params['slTriggerBy'] = 'Market'

        response = session.place_order(**params)
        logging.info(f"Conditional order placed for {symbol}: {response}")
    except Exception as err:
        logging.error(f"Error placing conditional order for {symbol}: {err}")

# --- Strategy Section ---
def calculate_atr_levels(df, current_price, side):
    """Calculates TP and SL levels based on Average True Range (ATR)."""
    if df is None or df.empty:
        return None, None
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    atr_value = df['ATR'].iloc[-1]
    
    if side == 'Buy':
        tp_price = current_price + (atr_value * atr_tp_multiplier)
        sl_price = current_price - (atr_value * atr_sl_multiplier)
    else:
        tp_price = current_price - (atr_value * atr_tp_multiplier)
        sl_price = current_price + (atr_value * atr_sl_multiplier)
    return tp_price, sl_price

def rsi_signal(df):
    """RSI crossover strategy."""
    if df is None or df.empty:
        return 'none'
    df['RSI'] = ta.rsi(df['Close'], length=14)
    if df['RSI'].iloc[-3] < 30 and df['RSI'].iloc[-2] < 30 and df['RSI'].iloc[-1] > 30:
        return 'up'
    if df['RSI'].iloc[-3] > 70 and df['RSI'].iloc[-2] > 70 and df['RSI'].iloc[-1] < 70:
        return 'down'
    return 'none'

def williams_r_signal(df):
    """Williams %R crossover strategy."""
    if df is None or df.empty:
        return 'none'
    df.ta.williams_r(length=24, append=True)
    df.ta.ema(close=df['WMR_24'], length=24, append=True)
    w = df['WMR_24']
    ema_w = df['EMA_24']
    if w.iloc[-1] < -99.5:
        return 'up'
    elif w.iloc[-1] > -0.5:
        return 'down'
    elif w.iloc[-1] < -75 and w.iloc[-2] < -75 and w.iloc[-2] < ema_w.iloc[-2] and w.iloc[-1] > ema_w.iloc[-1]:
        return 'up'
    elif w.iloc[-1] > -25 and w.iloc[-2] > -25 and w.iloc[-2] > ema_w.iloc[-2] and w.iloc[-1] < ema_w.iloc[-1]:
        return 'down'
    return 'none'

# --- Main Bot Loop ---
def main():
    max_pos = 5
    symbols = get_tickers()
    if not symbols:
        logging.info("No symbols found. Exiting.")
        return

    logging.info(f"Starting trading bot. Checking {len(symbols)} symbols.")

    ws = WebSocket(
        testnet=False,
        channel_type="linear"
    )
    for symbol in symbols:
        ws.kline_stream(symbol=symbol, interval=timeframe, callback=handle_message)
        sleep(0.5)

    logging.info("WebSocket connections established. Starting main loop.")

    while True:
        local_time, utc_time = get_current_time(timezone_str)
        logging.info(f"Local Time: {local_time.strftime('%Y-%m-%d %H:%M:%S')} | UTC Time: {utc_time.strftime('%Y-%m-%d %H:%M:%S')}")

        if not is_market_open(local_time):
            logging.info(f"Market is closed. Skipping this cycle. Waiting 2 minutes.")
            sleep(120)
            continue
            
        balance = get_balance()
        if balance is None:
            logging.error('Cannot connect to API. Waiting 2 mins and retrying.')
            sleep(120)
            continue
        
        logging.info(f'Current balance: {balance:.2f} USDT')
        
        pos = get_positions()
        logging.info(f'You have {len(pos)} positions: {pos}')

        for symbol in symbols:
            current_positions = get_positions()
            if len(current_positions) >= max_pos:
                logging.info("Max positions reached. Halting signal checks for this cycle.")
                break

            kl = klines(symbol)
            if kl is None:
                continue

            support, resistance = get_orderbook_levels(symbol)
            current_price = kl['Close'].iloc[-1]

            # Choose strategy
            signal = rsi_signal(kl)
            
            # Use orderbook analysis to decide on order type
            # You can adapt this logic to fit your specific strategy
            if signal == 'up' and support and abs(current_price - support) < (current_price * 0.005) and symbol not in current_positions:
                logging.info(f'Found BUY signal for {symbol} 📈, confirmed by strong support at {support}. Placing Limit Order.')
                
                price_precision, qty_precision = get_precisions(symbol)
                order_qty = round(qty / current_price, qty_precision)
                tp_price, sl_price = calculate_atr_levels(kl, current_price, 'Buy')

                set_mode(symbol)
                place_limit_order(
                    symbol=symbol,
                    side='Buy',
                    price=round(support, price_precision),
                    qty=order_qty,
                    tp_price=round(tp_price, price_precision),
                    sl_price=round(sl_price, price_precision)
                )

            elif signal == 'down' and resistance and abs(current_price - resistance) < (current_price * 0.005) and symbol not in current_positions:
                logging.info(f'Found SELL signal for {symbol} 📉, confirmed by strong resistance at {resistance}. Placing Limit Order.')
                
                price_precision, qty_precision = get_precisions(symbol)
                order_qty = round(qty / current_price, qty_precision)
                tp_price, sl_price = calculate_atr_levels(kl, current_price, 'Sell')

                set_mode(symbol)
                place_limit_order(
                    symbol=symbol,
                    side='Sell',
                    price=round(resistance, price_precision),
                    qty=order_qty,
                    tp_price=round(tp_price, price_precision),
                    sl_price=round(sl_price, price_precision)
                )
            # Example of a conditional breakout strategy
            elif williams_r_signal(kl) == 'up' and symbol not in current_positions and current_price > resistance:
                logging.info(f'Found breakout signal for {symbol} 📈. Placing Conditional Buy Order.')
                
                price_precision, qty_precision = get_precisions(symbol)
                order_qty = round(qty / current_price, qty_precision)
                tp_price, sl_price = calculate_atr_levels(kl, current_price, 'Buy')
                trigger_price = resistance + (resistance * 0.001) # 0.1% above resistance

                set_mode(symbol)
                place_conditional_order(
                    symbol=symbol,
                    side='Buy',
                    qty=order_qty,
                    trigger_price=round(trigger_price, price_precision),
                    order_type='Market',
                    tp_price=round(tp_price, price_precision),
                    sl_price=round(sl_price, price_precision)
                )

        logging.info('--- Cycle finished. Waiting 2 minutes for next loop. ---')
        sleep(120)

if __name__ == "__main__":
    main()

This video demonstrates how to place conditional orders on Bybit, which is a key part of the new functionality added to your bot template. [Bybit Conditional Order Tutorial](https://www.youtube.com/watch?v=n2IlrrDnB0c).
http://googleusercontent.com/youtube_content/17 *YouTube video views will be stored in your YouTube History, and your data will be stored and used by YouTube according to its [Terms of Service](https://www.youtube.com/static?template=terms)*



Adding Your Own Trading Strategy
To add your own strategy to this bot, you need to modify the code in the Strategy Section of the script. This is where the core decision-making logic resides. The process involves creating a new function that returns a trading signal ('up', 'down', or 'none') based on your custom indicators or rules.
Here's a step-by-step guide to integrate a new strategy into your bot:
Step 1: Choose Your Indicators
First, decide what technical indicators or market data you want to use for your strategy. The bot template already uses pandas_ta, which has hundreds of indicators. For this tutorial, we will use the Bollinger Bands and Stochastic RSI indicators to create a new strategy.
 * Bollinger Bands (BBANDS): Measures volatility and identifies overbought or oversold conditions. A common strategy is to buy when the price touches the lower band and sell when it touches the upper band.
 * Stochastic RSI (STOCHRSI): A momentum oscillator that measures the speed and change of price movements. It is used to identify overbought and oversold conditions and can signal a potential trend reversal.
Step 2: Write the Strategy Function
Create a new function that takes a pandas DataFrame (df) as input, as this is the format of the kline data from Bybit. Inside this function, you will use pandas_ta to calculate your chosen indicators and then write the logic to generate a signal.
Let's create a new function called bb_stoch_strategy.
def bb_stoch_strategy(df):
    """
    Bollinger Bands and Stochastic RSI trading strategy.
    Signal to buy when price touches the lower BB and StochRSI is oversold.
    Signal to sell when price touches the upper BB and StochRSI is overbought.
    """
    if df is None or df.empty:
        return 'none'
    
    # Calculate Bollinger Bands
    df.ta.bbands(close=df['Close'], length=20, append=True)
    
    # Calculate Stochastic RSI
    df.ta.stochrsi(close=df['Close'], length=14, append=True)
    
    # Get the last row of the DataFrame for analysis
    last_row = df.iloc[-1]
    
    # Check for a BUY signal
    # Condition 1: Price is below the lower Bollinger Band
    # Condition 2: Stochastic RSI K line is below 20 (oversold) and crossing above the D line
    if last_row['Close'] < last_row['BBL_20_2.0'] and last_row['STOCHRSIk_14_14_3_3'] < 20 and last_row['STOCHRSIk_14_14_3_3'] > last_row['STOCHRSId_14_14_3_3']:
        return 'up'
    
    # Check for a SELL signal
    # Condition 1: Price is above the upper Bollinger Band
    # Condition 2: Stochastic RSI K line is above 80 (overbought) and crossing below the D line
    if last_row['Close'] > last_row['BBU_20_2.0'] and last_row['STOCHRSIk_14_14_3_3'] > 80 and last_row['STOCHRSIk_14_14_3_3'] < last_row['STOCHRSId_14_14_3_3']:
        return 'down'
        
    return 'none'

 * df.ta.bbands: This adds three columns to your DataFrame for the upper, middle, and lower Bollinger Bands (BBU, BBM, BBL).
 * df.ta.stochrsi: This adds the Stochastic RSI K and D lines (STOCHRSIk, STOCHRSId) to your DataFrame.
 * Conditions: The if statements check the conditions. df.iloc[-1] accesses the most recent candle, allowing the bot to make decisions in real time.
Step 3: Integrate the Strategy into the Main Loop
Now, you need to tell the bot to use your new strategy function. In the main loop, find the line where the signal variable is assigned. You can either replace the existing strategy or add a conditional check to use your new one.
Original line:
signal = rsi_signal(kl)

Replace it with a call to your new function:
signal = bb_stoch_strategy(kl)

Or, to combine strategies, you can use a more advanced condition. For example, you can require both a momentum signal and a volatility signal to trigger a trade:
rsi_sig = rsi_signal(kl)
williams_sig = williams_r_signal(kl)
bb_stoch_sig = bb_stoch_strategy(kl)

# Combine signals for a more robust entry condition
if rsi_sig == 'up' and bb_stoch_sig == 'up':
    signal = 'up'
elif rsi_sig == 'down' and bb_stoch_sig == 'down':
    signal = 'down'
else:
    signal = 'none'

You now have a powerful, custom strategy integrated into your automated trading bot.
import random
from keys import api, secret, accountType
from helper import Bybit
from time import sleep
import ta
from threading import Thread

session = Bybit(api, secret, accountType)

tp = 0.02
sl = 0.015
mode = 1
leverage = 10
timeframe = 5
qty = 10
max_positions = 200


def rsi_signal(symbol):
    kl = session.klines(symbol, timeframe)
    rsi = ta.momentum.RSIIndicator(kl.Close).rsi()
    if rsi.iloc[-2] < 25:
        return 'buy'
    if rsi.iloc[-2] > 75:
        return 'sell'

qty = 10
symbols = session.get_tickers()
while True:
    try:
        balance = session.get_balance()
        # qty = balance * 0.3
        print(f'Balance: {round(balance, 3)} USDT')
        positions = session.get_positions()
        print(f'{len(positions)} Positions: {positions}')

        for symbol in symbols:
            positions = session.get_positions()
            if len(positions) >= max_positions:
                break
            sign = rsi_signal(symbol)
            if sign is not None and not symbol in positions:
                print(symbol, sign)
                session.place_order_market(symbol, sign, mode, leverage, qty, tp, sl)
                sleep(1)

        wait = 100
        print(f'Waiting {wait} sec')
        sleep(wait)
    except Exception as err:
        print(err)
        sleep(30)

from pybit.unified_trading import HTTP
import pandas as pd
import ta
from time import sleep
import random
import requests

class Bybit:
    def __init__(self, api, secret, accounttype):
        self.api = api
        self.secret = secret
        self.accountType = accounttype
        self.session = HTTP(api_key=self.api, api_secret=self.secret, testnet=True)

    def get_balance(self):
        try:
            resp = self.session.get_wallet_balance(accountType=self.accountType, coin="USDT", recv_window=40000)['result']['list'][0]['coin'][0]['walletBalance']
            resp = round(float(resp), 3)
            return resp
        except Exception as err:
            print(err)

    def get_positions(self):
        try:
            resp = self.session.get_positions(
                category='linear',
                settleCoin='USDT',
                recv_window = 40000
            )['result']['list']
            pos = []
            for elem in resp:
                pos.append(elem['symbol'])
            return pos
        except Exception as err:
            print(err)

    def get_last_pnl(self, limit=50):
        try:
            resp = self.session.get_closed_pnl(category="linear", limit=limit, recv_window=40000)['result']['list']
            pnl = 0
            for elem in resp:
                pnl += float(elem['closedPnl'])
            return round(pnl, 4)
        except Exception as err:
            print(err)

    def get_current_pnl(self):
        try:
            resp = self.session.get_positions(
                category="linear",
                settleCoin="USDT",
                recv_window=10000
            )['result']['list']
            pnl = 0
            for elem in resp:
                pnl += float(elem['unrealisedPnl'])
            return round(pnl, 4)
        except Exception as err:
            print(err)

    def get_tickers(self):
        try:
            resp = self.session.get_tickers(category="linear", recv_window=10000)['result']['list']
            symbols = []
            for elem in resp:
                if 'USDT' in elem['symbol'] and not 'USDC' in elem['symbol']:
                    symbols.append(elem['symbol'])
            return symbols
        except Exception as err:
            print(err)

    def klines(self, symbol, timeframe, limit=500):
        try:
            resp = self.session.get_kline(
                category='linear',
                symbol=symbol,
                interval=timeframe,
                limit=limit,
                recv_window=7000
            )['result']['list']
            resp = pd.DataFrame(resp)
            resp.columns = ['Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Turnover']
            resp = resp.set_index('Time')
            resp = resp.astype(float)
            resp = resp[::-1]
            return resp
        except Exception as err:
            print(err)

    def get_precisions(self, symbol):
        try:
            resp = self.session.get_instruments_info(
                category='linear',
                symbol=symbol,
                recv_window=10000
            )['result']['list'][0]
            price = resp['priceFilter']['tickSize']
            if '.' in price:
                price = len(price.split('.')[1])
            else:
                price = 0
            qty = resp['lotSizeFilter']['qtyStep']
            if '.' in qty:
                qty = len(qty.split('.')[1])
            else:
                qty = 0
            return price, qty
        except Exception as err:
            print(err)

    def get_max_leverage(self, symbol):
        try:
            resp = self.session.get_instruments_info(
                category="linear",
                symbol=symbol,
                recv_window=10000
            )['result']['list'][0]['leverageFilter']['maxLeverage']
            return float(resp)
        except Exception as err:
            print(err)

    def set_mode(self, symbol, mode=1, leverage=10):
        try:
            resp = self.session.switch_margin_mode(
                category='linear',
                symbol=symbol,
                tradeMode=str(mode),
                buyLeverage=str(leverage),
                sellLeverage=str(leverage),
                recv_window=10000
            )
            if resp['retMsg'] == 'OK':
                if mode == 1:
                    print(f'[{symbol}] Changed margin mode to ISOLATED')
                if mode == 0:
                    print(f'[{symbol}] Changed margin mode to CROSS')
        except Exception as err:
            if '110026' in str(err):
                print(f'[{symbol}] Margin mode is Not changed')
            else:
                print(err)

    def set_leverage(self, symbol, leverage=10):
        try:
            resp = self.session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage),
                recv_window=10000
            )
            if resp['retMsg'] == 'OK':
                print(f'[{symbol}] Changed leverage to {leverage}')
        except Exception as err:
            if '110043' in str(err):
                print(f'[{symbol}] Leverage is Not changed')
            else:
                print(err)

    def place_order_market(self, symbol, side, mode, leverage, qty=10, tp=0.012, sl=0.009):
        self.set_mode(symbol, mode, leverage)
        sleep(0.5)
        self.set_leverage(symbol, leverage)
        sleep(0.5)
        price_precision = self.get_precisions(symbol)[0]
        qty_precision = self.get_precisions(symbol)[1]
        mark_price = self.session.get_tickers(
            category='linear',
            symbol=symbol, recv_window=10000
        )['result']['list'][0]['markPrice']
        mark_price = float(mark_price)
        print(f'Placing {side} order for {symbol}. Mark price: {mark_price}')
        order_qty = round(qty / mark_price, qty_precision)
        sleep(2)
        if side == 'buy':
            try:
                tp_price = round(mark_price + mark_price * tp, price_precision)
                sl_price = round(mark_price - mark_price * sl, price_precision)
                resp = self.session.place_order(
                    category='linear',
                    symbol=symbol,
                    side='Buy',
                    orderType='Market',
                    qty=order_qty,
                    takeProfit=tp_price,
                    stopLoss=sl_price,
                    tpTriggerBy='Market',
                    slTriggerBy='Market', recv_window=10000
                )
                print(resp['retMsg'])
            except Exception as err:
                print(err)

        if side == 'sell':
            try:
                tp_price = round(mark_price - mark_price * tp, price_precision)
                sl_price = round(mark_price + mark_price * sl, price_precision)
                resp = self.session.place_order(
                    category='linear',
                    symbol=symbol,
                    side='Sell',
                    orderType='Market',
                    qty=order_qty,
                    takeProfit=tp_price,
                    stopLoss=sl_price,
                    tpTriggerBy='Market',
                    slTriggerBy='Market', recv_window=10000
                )
                print(resp['retMsg'])
            except Exception as err:
                print(err)

    def place_order_limit(self, symbol, side, mode, leverage, qty=10, tp=0.012, sl=0.009):
        self.set_mode(symbol, mode, leverage)
        sleep(0.5)
        self.set_leverage(symbol, leverage)
        sleep(0.5)
        price_precision = self.get_precisions(symbol)[0]
        qty_precision = self.get_precisions(symbol)[1]
        limit_price = self.session.get_tickers(
            category='linear',
            symbol=symbol
        )['result']['list'][0]['lastPrice']
        limit_price = float(limit_price)
        print(f'Placing {side} order for {symbol}. Limit price: {limit_price}')
        order_qty = round(qty / limit_price, qty_precision)
        sleep(2)
        if side == 'buy':
            try:
                tp_price = round(limit_price + limit_price * tp, price_precision)
                sl_price = round(limit_price - limit_price * sl, price_precision)
                resp = self.session.place_order(
                    category='linear',
                    symbol=symbol,
                    side='Buy',
                    orderType='Limit',
                    price= limit_price,
                    qty=order_qty,
                    takeProfit=tp_price,
                    stopLoss=sl_price,
                    tpTriggerBy='LastPrice',
                    slTriggerBy='LastPrice'
                )
                print(resp['retMsg'])
            except Exception as err:
                print(err)

        if side == 'sell':
            try:
                tp_price = round(limit_price - limit_price * tp, price_precision)
                sl_price = round(limit_price + limit_price * sl, price_precision)
                resp = self.session.place_order(
                    category='linear',
                    symbol=symbol,
                    side='Sell',
                    orderType='Limit',
                    price=limit_price,
                    qty=order_qty,
                    takeProfit=tp_price,
                    stopLoss=sl_price,
                    tpTriggerBy='LastPrice',
                    slTriggerBy='LastPrice'
                )
                print(resp['retMsg'])
            except Exception as err:
                print(err)

    def send_tg(self, key, tg_id, text):
        try:
            url = f'https://api.telegram.org/bot{key}/sendMessage'
            data = {
                'chat_id': tg_id,
                'text': text
            }
            resp = requests.post(url, data=data)
            print(resp)
        except Exception as err:
            print(err)
