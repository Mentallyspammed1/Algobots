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

# --- Helper for API Calls with Retry ---
def _make_api_call(api_client, method, endpoint, params=None, max_retries=3, initial_delay=1):
    """Generic function to make API calls with retry logic."""
    for attempt in range(max_retries):
        try:
            if method == 'get':
                response = getattr(api_client, endpoint)(**params) if params else getattr(api_client, endpoint)()
            elif method == 'post':
                response = getattr(api_client, endpoint)(**params)
            else:
                logging.error(f"Invalid method '{method}' for API call.")
                return {"retCode": 1, "retMsg": "Invalid method"}

            if response.get('retCode') == 0:
                return response
            else:
                ret_code = response.get('retCode')
                ret_msg = response.get('retMsg')
                logging.warning(f"API Error ({ret_code}): {ret_msg}. Retrying {endpoint} in {initial_delay * (2**attempt)}s... (Attempt {attempt + 1})")
                time.sleep(initial_delay * (2**attempt)) # Exponential backoff
        except Exception as e:
            logging.error(f"Network/Client error for {endpoint}: {e}. Retrying in {initial_delay * (2**attempt)}s... (Attempt {attempt + 1})")
            time.sleep(initial_delay * (2**attempt)) # Exponential backoff
    logging.error(f"Failed to complete API call to {endpoint} after {max_retries} attempts.")
    return {"retCode": 1, "retMsg": f"Failed after {max_retries} attempts: {endpoint}"}

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
    # Supertrend
    "supertrend_length": 10,
    "supertrend_multiplier": 3.0,
    # RSI
    "rsi_length": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    # Ehlers-Fisher
    "ef_period": 10,
    # MACD
    "macd_fast_period": 12,
    "macd_slow_period": 26,
    "macd_signal_period": 9,
    # Bollinger Bands
    "bb_period": 20,
    "bb_std_dev": 2.0,
    # Risk Management
    "riskPct": 1, # % of balance to risk per trade
    "leverage": 10,
    "stopLossPct": 2, # % from entry price
    "takeProfitPct": 5, # % from entry price
    "trailingStopPct": 0.5, # % from peak price for trailing stop loss
    # Simulation
    "initial_balance": 1000, # USDT
    "fee_rate": 0.0005, # Taker fee for Bybit (0.05%)
}

# --- Data Fetching ---
def fetch_historical_klines(symbol: str, interval: str, start_time: int, end_time: int) -> list:
    logging.info(f"Fetching historical klines for {symbol} ({interval}) from {datetime.datetime.fromtimestamp(start_time)} to {datetime.datetime.fromtimestamp(end_time)}")
    all_klines = []
    seen_timestamps = set()
    limit = 200 # Max limit per request
    current_time = end_time

    while current_time > start_time:
        # Bybit API expects endTime in milliseconds
        res = _make_api_call(
            bybit_session,
            'get',
            'get_kline',
            params={
                "category": DEFAULT_CONFIG["category"],
                "symbol": symbol,
                "interval": interval,
                "end": int(current_time * 1000),
                "limit": limit
            }
        )
        
        if res and res.get('retCode') == 0 and res['result']['list']:
            fetched_klines_list = res['result']['list']
            if not fetched_klines_list:
                logging.warning("API returned an empty list, stopping fetch.")
                break

            new_klines_added = 0
            for k in fetched_klines_list:
                ts = int(k[0])
                if ts not in seen_timestamps and (ts / 1000) >= start_time:
                    all_klines.append({
                        "timestamp": ts, "open": float(k[1]), "high": float(k[2]), 
                        "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])
                    })
                    seen_timestamps.add(ts)
                    new_klines_added += 1
            
            if new_klines_added == 0:
                # No new klines in the expected time range, stop to prevent infinite loops
                logging.info("No new, unique klines fetched in the last request. Assuming all historical data has been retrieved.")
                break

            # Move current_time to the oldest fetched kline for the next iteration
            oldest_ts_in_batch = int(fetched_klines_list[-1][0])
            current_time = oldest_ts_in_batch / 1000
            logging.info(f"Fetched {new_klines_added} new klines. Total: {len(all_klines)}. Oldest timestamp: {datetime.datetime.fromtimestamp(current_time)}")
            time.sleep(0.2) # Be nice to the API
        else:
            logging.error(f"Failed to fetch klines: {res.get('retMsg', 'No response')}")
            break
    
    # Sort by timestamp ascending
    klines = sorted(all_klines, key=lambda x: x['timestamp'])
    logging.info(f"Finished fetching. Total unique klines: {len(klines)}")
    return klines

# --- Backtesting Engine ---
def run_backtest(klines: list, config: dict) -> dict:
    logging.debug(f"Running backtest with config: {config}")
    balance = config["initial_balance"]
    position_size = 0
    entry_price = 0
    trades = []
    current_position_side = None # "Buy" or "Sell"

    # --- Metrics Initialization ---
    equity_curve = [balance]
    peak_equity = balance
    max_drawdown = 0
    gross_profit = 0
    gross_loss = 0

    last_supertrend_direction = 0
    peak_price = 0
    current_stop_loss_price = 0

    for i in range(len(klines)):
        current_kline = klines[i]
        current_price = current_kline['close']

        # Update equity curve based on open position's unrealized PnL
        if current_position_side:
            unrealized_pnl = 0
            if current_position_side == "Buy":
                unrealized_pnl = (current_price - entry_price) * position_size
            else:
                unrealized_pnl = (entry_price - current_price) * position_size
            current_equity = balance + unrealized_pnl
            peak_equity = max(peak_equity, current_equity)
            drawdown = (peak_equity - current_equity) / peak_equity if peak_equity > 0 else 0
            max_drawdown = max(max_drawdown, drawdown)
            equity_curve.append(current_equity)
        else:
            equity_curve.append(balance)

        # Ensure enough data for all indicators
        min_data_length = max(
            config['supertrend_length'], 
            config['rsi_length'], 
            config['ef_period'],
            config['macd_slow_period'],
            config['bb_period']
        )
        if i < min_data_length + 1:
            continue

        klines_for_indicators = klines[:i+1]
        indicators = calculate_indicators(klines_for_indicators, config)
        if not indicators: continue

        st = indicators['supertrend']
        rsi = indicators['rsi']
        fisher = indicators['fisher']
        macd = indicators['macd']
        bb = indicators['bollinger_bands']

        # --- Upgraded Multi-Confluence Signal Generation ---
        is_st_buy_signal = st['direction'] == 1 and last_supertrend_direction == -1
        is_st_sell_signal = st['direction'] == -1 and last_supertrend_direction == 1

        # Bullish confirmations
        buy_confirmations = [
            rsi < config['rsi_overbought'],
            fisher > 0,
            macd['macd_line'] > macd['signal_line'],
            current_price > bb['middle_band']
        ]
        
        # Bearish confirmations
        sell_confirmations = [
            rsi > config['rsi_oversold'],
            fisher < 0,
            macd['macd_line'] < macd['signal_line'],
            current_price < bb['middle_band']
        ]

        buy_signal = is_st_buy_signal and all(buy_confirmations)
        sell_signal = is_st_sell_signal and all(sell_confirmations)

        # --- Close Position Logic (SL/TP/Trailing) ---
        if current_position_side == "Buy" and position_size > 0:
            peak_price = max(peak_price, current_price)
            new_trailing_stop_price = peak_price * (1 - config['trailingStopPct'] / 100)
            if new_trailing_stop_price > current_stop_loss_price and new_trailing_stop_price > entry_price:
                current_stop_loss_price = new_trailing_stop_price

            sl_price = current_stop_loss_price
            tp_price = entry_price * (1 + config['takeProfitPct'] / 100)
            
            exit_price, exit_type = (sl_price, "SL") if current_price <= sl_price else (tp_price, "TP") if current_price >= tp_price else (None, None)

            if exit_price:
                pnl = (exit_price - entry_price) * position_size - (position_size * exit_price * config['fee_rate'])
                balance += pnl
                trades.append({"side": "Buy", "entry_price": entry_price, "exit_price": exit_price, "pnl": pnl, "type": exit_type})
                if pnl > 0: gross_profit += pnl
                else: gross_loss += abs(pnl)
                position_size, current_position_side, peak_price, current_stop_loss_price = 0, None, 0, 0

        elif current_position_side == "Sell" and position_size > 0:
            peak_price = min(peak_price, current_price)
            new_trailing_stop_price = peak_price * (1 + config['trailingStopPct'] / 100)
            if new_trailing_stop_price < current_stop_loss_price and new_trailing_stop_price < entry_price:
                current_stop_loss_price = new_trailing_stop_price

            sl_price = current_stop_loss_price
            tp_price = entry_price * (1 - config['takeProfitPct'] / 100)

            exit_price, exit_type = (sl_price, "SL") if current_price >= sl_price else (tp_price, "TP") if current_price <= tp_price else (None, None)

            if exit_price:
                pnl = (entry_price - exit_price) * position_size - (position_size * exit_price * config['fee_rate'])
                balance += pnl
                trades.append({"side": "Sell", "entry_price": entry_price, "exit_price": exit_price, "pnl": pnl, "type": exit_type})
                if pnl > 0: gross_profit += pnl
                else: gross_loss += abs(pnl)
                position_size, current_position_side, peak_price, current_stop_loss_price = 0, None, 0, 0

        # --- Open Position Logic ---
        if (buy_signal and current_position_side != "Buy") or (sell_signal and current_position_side != "Sell"):
            if current_position_side: # Close opposite position first
                close_price = current_price
                pnl = (close_price - entry_price) * position_size if current_position_side == "Buy" else (entry_price - close_price) * position_size
                pnl -= (position_size * close_price * config['fee_rate'])
                balance += pnl
                trades.append({"side": current_position_side, "entry_price": entry_price, "exit_price": close_price, "pnl": pnl, "type": "close_flip"})
                if pnl > 0: gross_profit += pnl
                else: gross_loss += abs(pnl)
                position_size, current_position_side, peak_price, current_stop_loss_price = 0, None, 0, 0

            side = "Buy" if buy_signal else "Sell"
            sl_pct = config['stopLossPct'] / 100
            
            if sl_pct > 0 and current_price > 0:
                position_value_usdt = (balance * (config['riskPct'] / 100)) / sl_pct
                if position_value_usdt >= 5: # MIN_ORDER_VALUE
                    new_position_size = position_value_usdt / current_price
                    max_leverage_size = (balance * config['leverage']) / current_price
                    position_size = min(new_position_size, max_leverage_size)
                    entry_price = current_price
                    current_position_side = side
                    balance -= (position_size * entry_price * config['fee_rate'])
                    trades.append({"side": side, "entry_price": entry_price, "qty": position_size, "type": "open"})
                    peak_price = entry_price
                    current_stop_loss_price = entry_price * (1 - sl_pct) if side == "Buy" else entry_price * (1 + sl_pct)

        last_supertrend_direction = st['direction']

    if position_size > 0: # Close any open position at the end
        exit_price = klines[-1]['close']
        pnl = (exit_price - entry_price) * position_size if current_position_side == "Buy" else (entry_price - exit_price) * position_size
        pnl -= (position_size * exit_price * config['fee_rate'])
        balance += pnl
        trades.append({"side": current_position_side, "entry_price": entry_price, "exit_price": exit_price, "pnl": pnl, "type": "final_close"})
        if pnl > 0: gross_profit += pnl
        else: gross_loss += abs(pnl)

    total_pnl = balance - config["initial_balance"]
    closed_trades = [t for t in trades if t['type'] not in ["open"]]
    num_trades = len(closed_trades)
    winning_trades = len([t for t in closed_trades if t['pnl'] > 0])
    win_rate = (winning_trades / num_trades * 100) if num_trades > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    final_log = f"Backtest finished. Final Balance: {balance:.2f} | PnL: {total_pnl:.2f} ({total_pnl/config['initial_balance']:.2%}) | Trades: {num_trades} | Win Rate: {win_rate:.2f}% | PF: {profit_factor:.2f} | MDD: {max_drawdown:.2%}"
    logging.debug(final_log)
    
    return {"total_pnl_pct": total_pnl/config["initial_balance"], "total_pnl": total_pnl, "num_trades": num_trades, "win_rate": win_rate, "final_balance": balance, "profit_factor": profit_factor, "max_drawdown": max_drawdown, "trades": trades, "equity_curve": equity_curve, "config": config}

# --- Optimization Engine (Grid Search) ---
def optimize_strategy(klines: list, param_ranges: dict, min_trades_threshold=10) -> dict:
    import json, itertools
    best_result, best_pnl_pct = None, -float('inf')
    keys = list(param_ranges.keys())
    param_combinations = list(itertools.product(*param_ranges.values()))
    total_combinations = len(param_combinations)
    logging.info(f"Starting optimization for {total_combinations} combinations...")
    
    for i, combo in enumerate(param_combinations):
        current_config = DEFAULT_CONFIG.copy()
        for j, key in enumerate(keys): current_config[key] = combo[j]
        
        result = run_backtest(klines, current_config)

        if result["total_pnl_pct"] > best_pnl_pct and result["num_trades"] >= min_trades_threshold:
            best_pnl_pct = result["total_pnl_pct"]
            best_result = result
            logging.info(f"\n*** NEW BEST PNL: {best_pnl_pct:.2%} (Trades: {result['num_trades']}, PF: {result['profit_factor']:.2f}, MDD: {result['max_drawdown']:.2%}) ***")
        
        progress = (i + 1) / total_combinations
        progress_bar = '#' * int(progress * 40)
        print(f"Progress: [{progress_bar:<40}] {progress:.1%} | Best PNL: {best_pnl_pct:.2%}", end='\r')

    print("\n")
    logging.info("--- Optimization Complete ---")
    
    if best_result:
        try:
            symbol, interval = best_result['config']['symbol'], best_result['config']['interval']
            result_filename = f"best_backtest_results_{symbol}_{interval}.json"
            serializable_result = best_result.copy()
            serializable_result['config'] = {k: str(v) for k, v in best_result['config'].items()}
            with open(result_filename, 'w') as f: json.dump(serializable_result, f, indent=4)
            logging.info(f"Full results of the best run saved to {result_filename}")
        except Exception as e: logging.error(f"Failed to save best result to JSON file: {e}")
    else:
        logging.info(f"No profitable strategy found that met the minimum trade threshold of {min_trades_threshold}.")
        
    return best_result

# --- Main Execution ---
if __name__ == "__main__":
    end_timestamp = int(datetime.datetime.now().timestamp())
    start_timestamp = int((datetime.datetime.now() - datetime.timedelta(days=180)).timestamp())

    historical_klines = fetch_historical_klines(DEFAULT_CONFIG["symbol"], DEFAULT_CONFIG["interval"], start_timestamp, end_timestamp)

    if historical_klines:
        param_ranges = {
            "supertrend_length": [9, 10, 11, 12],
            "supertrend_multiplier": [2.0, 2.5, 3.0, 3.5],
            "rsi_length": [10, 14, 18],
            "rsi_overbought": [65, 70, 75],
            "rsi_oversold": [25, 30, 35],
            "ef_period": [8, 10, 12],
            "riskPct": [0.5, 1.0, 1.5],
            "leverage": [10, 20],
            "stopLossPct": [1.0, 1.5, 2.0],
            "takeProfitPct": [3.0, 4.0, 5.0, 6.0],
            "trailingStopPct": [0.2, 0.5, 0.8, 1.0],
            "macd_fast_period": [10, 12, 14],
            "macd_slow_period": [24, 26, 28],
            "macd_signal_period": [8, 9, 10],
            "bb_period": [18, 20, 22],
            "bb_std_dev": [1.8, 2.0, 2.2],
        }

        best_result = optimize_strategy(historical_klines, param_ranges, min_trades_threshold=20)
        
        if best_result:
            print("\n" + "="*60)
            print("           OPTIMIZATION COMPLETE - BEST STRATEGY FOUND")
            print("="*60)
            print(f"Total PnL:         {best_result['total_pnl']:.2f} USDT ({best_result['total_pnl_pct']:.2%})")
            print(f"Final Balance:     {best_result['final_balance']:.2f} USDT")
            print(f"Total Trades:      {best_result['num_trades']}")
            print(f"Win Rate:          {best_result['win_rate']:.2f}%")
            print(f"Profit Factor:     {best_result['profit_factor']:.2f}")
            print(f"Maximum Drawdown:  {best_result['max_drawdown']:.2%}")
            print("-"*60)
            print("OPTIMIZED PARAMETERS:")
            for k, v in best_result['config'].items():
                if k in param_ranges: print(f"  {k}: {v}")
            print("="*60)
            print(f"\nFull report saved to: best_backtest_results_{best_result['config']['symbol']}_{best_result['config']['interval']}.json")
            print("To use these parameters, update them in your live trading configuration.\n")
        else:
            print("\nOptimization finished, but no profitable configuration was found.")
    else:
        logging.error("No historical klines fetched. Cannot run backtest or optimization.")
