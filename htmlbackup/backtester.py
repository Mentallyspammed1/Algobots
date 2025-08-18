import os
import time
import datetime
import logging
from pybit.unified_trading import HTTP
from dotenv import load_dotenv
from indicators import calculate_indicators

# --- Configuration ---
load_dotenv()

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Bybit Session (for historical data) ---
# Use testnet for fetching historical data if you don't want to use live API keys for this.
# For backtesting, you might want to fetch from live if your keys allow.
bybit_session = HTTP(
    testnet=False, # Set to True if you want to use testnet for data fetching
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET
)

# --- Backtesting Parameters (to be optimized) ---
DEFAULT_CONFIG = {
    "symbol": "BTCUSDT",
    "category": "linear",
    "interval": "60", # 1, 5, 15, 30, 60, 240, D
    "supertrend_length": 10,
    "supertrend_multiplier": 3.0,
    "rsi_length": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "ef_period": 10,
    "riskPct": 1, # % of balance to risk per trade
    "leverage": 10,
    "stopLossPct": 2, # % from entry price
    "takeProfitPct": 5, # % from entry price
    "trailingStopPct": 0.5, # % from peak price for trailing stop loss
    "initial_balance": 1000, # USDT
    "fee_rate": 0.0005, # Taker fee for Bybit (0.05%)
}

# --- Data Fetching ---
def fetch_historical_klines(symbol: str, interval: str, start_time: int, end_time: int) -> list:
    logging.info(f"Fetching historical klines for {symbol} ({interval}) from {start_time} to {end_time}")
    klines = []
    limit = 200 # Max limit per request
    current_time = end_time

    while current_time > start_time:
        # Bybit API expects endTime in milliseconds
        res = bybit_session.get_kline(
            category=DEFAULT_CONFIG["category"],
            symbol=symbol,
            interval=interval,
            end=int(current_time * 1000),
            limit=limit
        )
        
        if res and res['retCode'] == 0 and res['result']['list']:
            fetched_klines = sorted([{
                "timestamp": int(k[0]), "open": float(k[1]), "high": float(k[2]), 
                "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])
            } for k in res['result']['list']], key=lambda x: x['timestamp'], reverse=True)
            
            # Filter out klines older than start_time
            fetched_klines = [k for k in fetched_klines if k['timestamp'] / 1000 >= start_time]
            
            klines.extend(fetched_klines)
            current_time = klines[-1]['timestamp'] / 1000 # Move current_time to the oldest fetched kline
            logging.info(f"Fetched {len(fetched_klines)} klines. Total: {len(klines)}. Oldest timestamp: {datetime.datetime.fromtimestamp(current_time)}")
            time.sleep(0.1) # Be nice to the API
        else:
            logging.error(f"Failed to fetch klines: {res}")
            break
    
    # Sort by timestamp ascending
    klines = sorted(klines, key=lambda x: x['timestamp'])
    logging.info(f"Finished fetching. Total klines: {len(klines)}")
    return klines

# --- Backtesting Engine ---
def run_backtest(klines: list, config: dict) -> dict:
    logging.info(f"Running backtest with config: {config}")
    balance = config["initial_balance"]
    position_size = 0
    entry_price = 0
    trades = []
    current_position_side = None # "Buy" or "Sell"

    # Keep track of previous indicator values for signal generation
    last_supertrend_direction = 0
    peak_price = 0 # For trailing stop loss
    current_stop_loss_price = 0 # Current active stop loss price

    for i in range(len(klines)):
        current_kline = klines[i]
        current_price = current_kline['close']

        # Ensure enough data for indicators
        if i < max(config['supertrend_length'], config['rsi_length'], config['ef_period']) + 1:
            continue

        # Slice klines for indicator calculation (simulating real-time data)
        klines_for_indicators = klines[:i+1]
        indicators = calculate_indicators(klines_for_indicators, config)

        if not indicators:
            continue

        supertrend = indicators['supertrend']
        rsi = indicators['rsi']
        fisher = indicators['fisher']

        # Signal generation
        buy_signal = supertrend['direction'] == 1 and last_supertrend_direction == -1 and rsi < config['rsi_overbought'] and fisher > 0
        sell_signal = supertrend['direction'] == -1 and last_supertrend_direction == 1 and rsi > config['rsi_oversold'] and fisher < 0

        # Trading Logic
        if buy_signal and current_position_side != "Buy":
            # Close existing short position if any
            if current_position_side == "Sell":
                pnl = (entry_price - current_price) * position_size - (position_size * current_price * config['fee_rate'])
                balance += pnl
                trades.append({"side": "Sell", "entry_price": entry_price, "exit_price": current_price, "pnl": pnl, "type": "close"})
                logging.debug(f"Closed short at {current_price:.2f} PnL: {pnl:.2f} Balance: {balance:.2f}")
                position_size = 0
                current_position_side = None
            
            # Open new long position
            risk_amount = balance * (config['riskPct'] / 100)
            sl_price = current_price * (1 - config['stopLossPct'] / 100)
            stop_distance = abs(current_price - sl_price)
            
            if stop_distance > 0:
                # Calculate position size based on risk percentage and stop loss percentage
                # qty for USDT perpetuals is the USDT value of the order
                qty = (balance * (config['riskPct'] / 100)) / (config['stopLossPct'] / 100)

                MIN_ORDER_VALUE = 5 # Default minimum order value in USDT
                if qty < MIN_ORDER_VALUE:
                    logging.debug(f"Calculated quantity {qty:.4f} is less than minimum order value {MIN_ORDER_VALUE}. Order not placed.")
                    continue # Skip order placement if qty is too small

                # Adjust qty based on current price and balance to avoid over-leveraging
                # This part of the original logic is still relevant to ensure we don't exceed available balance
                max_qty_from_balance = (balance * config['leverage']) / current_price
                qty = min(qty, max_qty_from_balance) # Ensure we don't open a position larger than our balance allows

                if qty * current_price > 10: # Minimum order size (e.g., 10 USDT) - this check is now redundant with MIN_ORDER_VALUE but kept for safety
                    position_size = qty
                    entry_price = current_price
                    current_position_side = "Buy"
                    balance -= (position_size * entry_price * config['fee_rate']) # Deduct entry fee
                    trades.append({"side": "Buy", "entry_price": entry_price, "qty": position_size, "type": "open"})
                    logging.debug(f"Opened long at {entry_price:.2f} Qty: {position_size:.4f} Balance: {balance:.2f}")
                    peak_price = current_price # Initialize peak price for trailing stop
                    current_stop_loss_price = sl_price # Initialize current stop loss price

        elif sell_signal and current_position_side != "Sell":
            # Close existing long position if any
            if current_position_side == "Buy":
                pnl = (current_price - entry_price) * position_size - (position_size * current_price * config['fee_rate'])
                balance += pnl
                trades.append({"side": "Buy", "entry_price": entry_price, "exit_price": current_price, "pnl": pnl, "type": "close"})
                logging.debug(f"Closed long at {current_price:.2f} PnL: {pnl:.2f} Balance: {balance:.2f}")
                position_size = 0
                current_position_side = None

            # Open new short position
            risk_amount = balance * (config['riskPct'] / 100)
            sl_price = current_price * (1 + config['stopLossPct'] / 100)
            stop_distance = abs(current_price - sl_price)

            if stop_distance > 0:
                # Calculate position size based on risk percentage and stop loss percentage
                # qty for USDT perpetuals is the USDT value of the order
                qty = (balance * (config['riskPct'] / 100)) / (config['stopLossPct'] / 100)

                MIN_ORDER_VALUE = 5 # Default minimum order value in USDT
                if qty < MIN_ORDER_VALUE:
                    logging.debug(f"Calculated quantity {qty:.4f} is less than minimum order value {MIN_ORDER_VALUE}. Order not placed.")
                    continue # Skip order placement if qty is too small

                max_qty_from_balance = (balance * config['leverage']) / current_price
                qty = min(qty, max_qty_from_balance)

                if qty * current_price > 10: # Minimum order size
                    position_size = qty
                    entry_price = current_price
                    current_position_side = "Sell"
                    balance -= (position_size * entry_price * config['fee_rate']) # Deduct entry fee
                    trades.append({"side": "Sell", "entry_price": entry_price, "qty": position_size, "type": "open"})
                    logging.debug(f"Opened short at {entry_price:.2f} Qty: {position_size:.4f} Balance: {balance:.2f}")
                    peak_price = current_price # Initialize peak price for trailing stop
                    current_stop_loss_price = sl_price # Initialize current stop loss price

        # Handle Stop Loss / Take Profit (simplified for backtesting)
        if current_position_side == "Buy" and position_size > 0:
            # Update peak price for trailing stop
            peak_price = max(peak_price, current_price)
            
            # Calculate new trailing stop price
            trailing_stop_pct = config['trailingStopPct'] / 100
            new_trailing_stop_price = peak_price * (1 - trailing_stop_pct)

            # If new trailing stop is more favorable and in profit, update current_stop_loss_price
            if new_trailing_stop_price > current_stop_loss_price and new_trailing_stop_price > entry_price:
                current_stop_loss_price = new_trailing_stop_price
                logging.debug(f"Trailing SL (long) moved to {current_stop_loss_price:.2f}")

            sl_price = current_stop_loss_price # Use the potentially trailed stop loss
            tp_price = entry_price * (1 + config['takeProfitPct'] / 100)
            if current_price <= sl_price:
                pnl = (sl_price - entry_price) * position_size - (position_size * sl_price * config['fee_rate'])
                balance += pnl
                trades.append({"side": "Buy", "entry_price": entry_price, "exit_price": sl_price, "pnl": pnl, "type": "SL"})
                logging.debug(f"SL hit (long) at {sl_price:.2f} PnL: {pnl:.2f} Balance: {balance:.2f}")
                position_size = 0
                current_position_side = None
                peak_price = 0 # Reset peak price
                current_stop_loss_price = 0 # Reset current stop loss
            elif current_price >= tp_price:
                pnl = (tp_price - entry_price) * position_size - (position_size * tp_price * config['fee_rate'])
                balance += pnl
                trades.append({"side": "Buy", "entry_price": entry_price, "exit_price": tp_price, "pnl": pnl, "type": "TP"})
                logging.debug(f"TP hit (long) at {tp_price:.2f} PnL: {pnl:.2f} Balance: {balance:.2f}")
                position_size = 0
                current_position_side = None
                peak_price = 0 # Reset peak price
                current_stop_loss_price = 0 # Reset current stop loss

        elif current_position_side == "Sell" and position_size > 0:
            # Update peak price for trailing stop
            peak_price = min(peak_price, current_price)

            # Calculate new trailing stop price
            trailing_stop_pct = config['trailingStopPct'] / 100
            new_trailing_stop_price = peak_price * (1 + trailing_stop_pct)

            # If new trailing stop is more favorable and in profit, update current_stop_loss_price
            if new_trailing_stop_price < current_stop_loss_price and new_trailing_stop_price < entry_price:
                current_stop_loss_price = new_trailing_stop_price
                logging.debug(f"Trailing SL (short) moved to {current_stop_loss_price:.2f}")

            sl_price = current_stop_loss_price # Use the potentially trailed stop loss
            tp_price = entry_price * (1 - config['takeProfitPct'] / 100)
            if current_price >= sl_price:
                pnl = (entry_price - sl_price) * position_size - (position_size * sl_price * config['fee_rate'])
                balance += pnl
                trades.append({"side": "Sell", "entry_price": entry_price, "exit_price": sl_price, "pnl": pnl, "type": "SL"})
                logging.debug(f"SL hit (short) at {sl_price:.2f} PnL: {pnl:.2f} Balance: {balance:.2f}")
                position_size = 0
                current_position_side = None
                peak_price = 0 # Reset peak price
                current_stop_loss_price = 0 # Reset current stop loss
            elif current_price <= tp_price:
                pnl = (entry_price - tp_price) * position_size - (position_size * tp_price * config['fee_rate'])
                balance += pnl
                trades.append({"side": "Sell", "entry_price": entry_price, "exit_price": tp_price, "pnl": pnl, "type": "TP"})
                logging.debug(f"TP hit (short) at {tp_price:.2f} PnL: {pnl:.2f} Balance: {balance:.2f}")
                position_size = 0
                current_position_side = None
                peak_price = 0 # Reset peak price
                current_stop_loss_price = 0 # Reset current stop loss

        last_supertrend_direction = supertrend['direction']

    # Close any open position at the end of the backtest
    if position_size > 0:
        pnl = 0
        if current_position_side == "Buy":
            pnl = (klines[-1]['close'] - entry_price) * position_size - (position_size * klines[-1]['close'] * config['fee_rate'])
        else:
            pnl = (entry_price - klines[-1]['close']) * position_size - (position_size * klines[-1]['close'] * config['fee_rate'])
        balance += pnl
        trades.append({"side": current_position_side, "entry_price": entry_price, "exit_price": klines[-1]['close'], "pnl": pnl, "type": "final_close"})
        logging.debug(f"Final close at {klines[-1]['close']:.2f} PnL: {pnl:.2f} Balance: {balance:.2f}")

    total_pnl = balance - config["initial_balance"]
    num_trades = len([t for t in trades if t['type'] in ["close", "SL", "TP", "final_close"]])
    winning_trades = len([t for t in trades if t['type'] in ["close", "TP", "final_close"] and t['pnl'] > 0])
    win_rate = (winning_trades / num_trades * 100) if num_trades > 0 else 0

    logging.info(f"Backtest finished. Total PnL: {total_pnl:.2f} USDT. Trades: {num_trades}. Win Rate: {win_rate:.2f}%")
    return {"total_pnl": total_pnl, "num_trades": num_trades, "win_rate": win_rate, "final_balance": balance, "trades": trades}

# --- Optimization Engine (Grid Search) ---
def optimize_strategy(klines: list, param_ranges: dict) -> dict:
    best_pnl = -float('inf')
    best_config = None

    # Generate all combinations of parameters
    keys = list(param_ranges.keys())
    import itertools
    param_combinations = itertools.product(*param_ranges.values())

    total_combinations = len(list(itertools.product(*param_ranges.values())))
    logging.info(f"Starting optimization for {total_combinations} combinations...")
    
    for i, combo in enumerate(param_combinations):
        current_config = DEFAULT_CONFIG.copy()
        for j, key in enumerate(keys):
            current_config[key] = combo[j]
        
        logging.info(f"Testing combination {i+1}/{total_combinations}: {current_config}")
        result = run_backtest(klines, current_config)

        if result["total_pnl"] > best_pnl:
            best_pnl = result["total_pnl"]
            best_config = current_config
            logging.info(f"New best PnL: {best_pnl:.2f} with config: {best_config}")
    
    logging.info(f"Optimization complete. Best PnL: {best_pnl:.2f} with config: {best_config}")
    return best_config

# --- Main Execution ---
if __name__ == "__main__":
    # Define the time range for historical data (e.g., last 3 months)
    end_timestamp = int(datetime.datetime.now().timestamp())
    start_timestamp = int((datetime.datetime.now() - datetime.timedelta(days=90)).timestamp())

    # Fetch data
    historical_klines = fetch_historical_klines(
        symbol=DEFAULT_CONFIG["symbol"],
        interval=DEFAULT_CONFIG["interval"],
        start_time=start_timestamp,
        end_time=end_timestamp
    )

    if historical_klines:
        # Define parameter ranges for optimization
        # Example ranges - adjust as needed
        param_ranges = {
            "supertrend_length": [7, 8, 9, 10, 11, 12],
            "supertrend_multiplier": [2.0, 2.5, 3.0, 3.5],
            "rsi_length": [12, 14, 16],
            "rsi_overbought": [65, 70, 75],
            "rsi_oversold": [25, 30, 35],
            "ef_period": [8, 10, 12],
            "riskPct": [0.5, 1.0, 1.5],
            "leverage": [5, 10, 20],
            "stopLossPct": [1.0, 1.5, 2.0],
            "takeProfitPct": [3.0, 4.0, 5.0],
            "trailingStopPct": [0.2, 0.5, 0.8],
        }

        # Run optimization
        best_params = optimize_strategy(historical_klines, param_ranges)
        print("\n--- Best Optimized Parameters ---")
        for k, v in best_params.items():
            print(f"{k}: {v}")
        print("---------------------------------")

        # You can then use these best_params in your live trading bot config
        # For example, update the config in supertrend.html or backbone.py with these values.
    else:
        logging.error("No historical klines fetched. Cannot run backtest or optimization.")
