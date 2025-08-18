import os
import time
import json
import logging
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from pybit.unified_trading import HTTP
import google.generativeai as genai
from indicators import calculate_indicators

# --- Basic Setup ---
load_dotenv()
app = Flask(__name__)
CORS(app)

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- API Key Configuration ---
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not BYBIT_API_KEY or not BYBIT_API_SECRET:
    logging.error("CRITICAL: Bybit API Key or Secret not found. Please check your .env file.")
if not GEMINI_API_KEY:
    logging.warning("Gemini API Key not found. The insight feature will be disabled.")
else:
    genai.configure(api_key=GEMINI_API_KEY)

# --- Global Bot State ---
# This dictionary will hold the state of our trading bot.
# It's a simple way to manage state in a single-threaded Flask app with a background worker.
BOT_STATE = {
    "running": False,
    "thread": None,
    "config": {},
    "bybit_session": None,
    "logs": [],
    "trade_history": {"wins": 0, "losses": 0, "history": []},
    "dashboard": {
        "currentPrice": "---",
        "priceChange": "---",
        "stDirection": "---",
        "stValue": "---",
        "rsiValue": "---",
        "rsiStatus": "---",
        "currentPosition": "None",
        "positionPnL": "---",
        "accountBalance": "---",
        "totalTrades": 0,
        "winRate": "0%",
        "botStatus": "Idle",
    },
    "last_supertrend": {"direction": 0, "value": 0},
    "previous_close": 0,
}

# --- Logging ---
def log_message(message, level='info'):
    """Adds a message to the in-memory log."""
    timestamp = time.strftime("%H:%M:%S")
    BOT_STATE["logs"].append({"timestamp": timestamp, "level": level, "message": message})
    # Keep logs from growing indefinitely
    if len(BOT_STATE["logs"]) > 200:
        BOT_STATE["logs"].pop(0)
    # Also log to console
    if level == 'error':
        logging.error(message)
    elif level == 'warning':
        logging.warning(message)
    else:
        logging.info(message)

# --- Trading Logic ---
def trading_bot_loop():
    """The main loop for the trading bot, running in a separate thread."""
    log_message("Trading bot thread started.", "success")
    
    while BOT_STATE.get("running"):
        try:
            config = BOT_STATE["config"]
            session = BOT_STATE["bybit_session"]
            dashboard = BOT_STATE["dashboard"]

            dashboard["botStatus"] = "Scanning"
            
            # 1. Fetch Kline Data
            klines_res = session.get_kline(category="linear", symbol=config["symbol"], interval=config["interval"], limit=200)
            if klines_res.get('retCode') != 0:
                log_message(f"Failed to fetch klines: {klines_res.get('retMsg')}", "error")
                time.sleep(int(config["interval"]) * 60)
                continue

            klines = sorted([{
                "timestamp": int(k[0]), "open": float(k[1]), "high": float(k[2]), 
                "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])
            } for k in klines_res['result']['list']], key=lambda x: x['timestamp'])

            current_price = klines[-1]['close']
            
            # 2. Calculate Indicators
            indicators = calculate_indicators(klines, config)
            if not indicators:
                log_message("Insufficient data for indicators.", "warning")
                dashboard["botStatus"] = "Waiting"
                time.sleep(int(config["interval"]) * 60)
                continue

            # 3. Fetch Position and Balance
            position_res = session.get_positions(category="linear", symbol=config["symbol"])
            balance_res = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")

            current_position = None
            if position_res.get('retCode') == 0:
                pos_list = [p for p in position_res['result']['list'] if float(p.get('size', 0)) > 0]
                if pos_list:
                    current_position = pos_list[0]
            
            balance = 0
            if balance_res.get('retCode') == 0 and balance_res['result']['list']:
                balance = float(balance_res['result']['list'][0]['totalWalletBalance'])

            # 4. Update Dashboard
            dashboard['currentPrice'] = f"${current_price:.{config['price_precision']}f}"
            st = indicators['supertrend']
            dashboard['stDirection'] = "UPTREND" if st['direction'] == 1 else "DOWNTREND"
            dashboard['stValue'] = f"{st['supertrend']:.{config['price_precision']}f}"
            dashboard['rsiValue'] = f"{indicators['rsi']:.2f}"
            dashboard['accountBalance'] = f"${balance:.2f}"
            dashboard['fisherValue'] = f"{indicators['fisher']:.2f}"
            if current_position:
                dashboard['currentPosition'] = f"{current_position['side']} {current_position['size']}"
                pnl = (current_price - float(current_position['avgPrice'])) * float(current_position['size']) if current_position['side'] == 'Buy' else (float(current_position['avgPrice']) - current_price) * float(current_position['size'])
                dashboard['positionPnL'] = f"{pnl:.2f} USDT"
            else:
                dashboard['currentPosition'] = "None"
                dashboard['positionPnL'] = "---"

            # 5. Core Trading Logic
            fisher = indicators['fisher']
            buy_signal = st['direction'] == 1 and BOT_STATE["last_supertrend"]['direction'] == -1 and indicators['rsi'] < config['rsi_overbought'] and fisher > 0 # Ehlers-Fisher confirmation
            sell_signal = st['direction'] == -1 and BOT_STATE["last_supertrend"]['direction'] == 1 and indicators['rsi'] > config['rsi_oversold'] and fisher < 0 # Ehlers-Fisher confirmation

            if buy_signal or sell_signal:
                side = "Buy" if buy_signal else "Sell"
                log_message(f"{side.upper()} SIGNAL DETECTED!", "signal")
                
                # Close existing position if it's opposite
                if current_position and current_position['side'] != side:
                    log_message(f"Closing opposite {current_position['side']} position.", "warning")
                    session.place_order(category="linear", symbol=config["symbol"], side="Sell" if current_position['side'] == "Buy" else "Buy", orderType="Market", qty=current_position['size'], reduceOnly=True)
                    time.sleep(2) # Give time for position to close
                    balance_res = session.get_wallet_balance(accountType="UNIFIED", coin="USDT") # Refresh balance
                    if balance_res.get('retCode') == 0 and balance_res['result']['list']:
                        balance = float(balance_res['result']['list'][0]['totalWalletBalance'])

                # Place new order
                risk_amount = balance * (config['riskPct'] / 100)
                sl_price = current_price * (1 - config['stopLossPct'] / 100) if side == 'Buy' else current_price * (1 + config['stopLossPct'] / 100)
                tp_price = current_price * (1 + config['takeProfitPct'] / 100) if side == 'Buy' else current_price * (1 - config['takeProfitPct'] / 100)
                
                stop_distance = abs(current_price - sl_price)
                if stop_distance > 0:
                    qty = (risk_amount / stop_distance) * config['leverage'] # Simplified qty calc
                    
                    log_message(f"Placing {side} order for {qty:.{config['qty_precision']}f} {config['symbol']}", "info")
                    order_res = session.place_order(
                        category="linear",
                        symbol=config["symbol"],
                        side=side,
                        orderType="Market",
                        qty=f"{qty:.{config['qty_precision']}f}",
                        takeProfit=f"{tp_price:.{config['price_precision']}f}",
                        stopLoss=f"{sl_price:.{config['price_precision']}f}",
                        tpslMode="Full"
                    )
                    if order_res.get('retCode') == 0:
                        log_message("Order placed successfully.", "success")
                    else:
                        log_message(f"Order failed: {order_res.get('retMsg')}", "error")

            BOT_STATE["last_supertrend"] = indicators['supertrend']
            dashboard["botStatus"] = "Idle"

        except Exception as e:
            log_message(f"An error occurred in the trading loop: {e}", "error")
            dashboard["botStatus"] = "Error"
        
        # Wait for the next interval
        interval_seconds = 60
        try:
            if BOT_STATE["config"]["interval"] == 'D':
                interval_seconds = 86400
            else:
                interval_seconds = int(BOT_STATE["config"]["interval"]) * 60
        except:
            pass # Keep default
        
        time.sleep(interval_seconds)

    log_message("Trading bot thread stopped.", "warning")


# --- Flask API Endpoints ---
@app.route('/api/start', methods=['POST'])
def start_bot():
    if BOT_STATE["running"]:
        return jsonify({"status": "error", "message": "Bot is already running."}), 400

    config = request.json
    api_key = config.pop("apiKey")
    api_secret = config.pop("apiSecret")

    if not api_key or not api_secret:
        return jsonify({"status": "error", "message": "API key and secret are required."}), 400

    BOT_STATE["config"] = config
    BOT_STATE["config"]['ef_period'] = config.get('ef_period', 10) # Default Ehlers-Fisher period
    BOT_STATE["bybit_session"] = HTTP(testnet=False, api_key=api_key, api_secret=api_secret) # LIVE TRADING

    # Verify API connection
    balance_check = BOT_STATE["bybit_session"].get_wallet_balance(accountType="UNIFIED", coin="USDT")
    if balance_check.get("retCode") != 0:
        return jsonify({"status": "error", "message": f"API connection failed: {balance_check.get('retMsg')}"}), 400
    
    log_message("API connection successful.", "success")

    # Set leverage
    leverage = config.get('leverage', 10)
    lev_res = BOT_STATE["bybit_session"].set_leverage(category="linear", symbol=config['symbol'], buyLeverage=str(leverage), sellLeverage=str(leverage))
    if lev_res.get('retCode') == 0:
        log_message(f"Leverage set to {leverage}x for {config['symbol']}", "success")
    else:
        log_message(f"Failed to set leverage: {lev_res.get('retMsg')}", "warning")


    BOT_STATE["running"] = True
    BOT_STATE["thread"] = threading.Thread(target=trading_bot_loop, daemon=True)
    BOT_STATE["thread"].start()

    return jsonify({"status": "success", "message": "Bot started successfully."})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    if not BOT_STATE["running"]:
        return jsonify({"status": "error", "message": "Bot is not running."}), 400

    BOT_STATE["running"] = False
    if BOT_STATE["thread"] and BOT_STATE["thread"].is_alive():
        BOT_STATE["thread"].join(timeout=5) # Wait for thread to finish

    BOT_STATE["thread"] = None
    BOT_STATE["bybit_session"] = None
    BOT_STATE["dashboard"]["botStatus"] = "Idle"
    log_message("Bot has been stopped by user.", "warning")
    
    return jsonify({"status": "success", "message": "Bot stopped."})

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({
        "running": BOT_STATE["running"],
        "dashboard": BOT_STATE["dashboard"],
        "logs": BOT_STATE["logs"]
    })

@app.route('/api/gemini-insight', methods=['POST'])
def get_gemini_insight():
    if not GEMINI_API_KEY:
        return jsonify({"status": "error", "message": "Gemini API key not configured on server."}), 503
    
    data = request.json
    prompt = data.get('prompt')
    if not prompt:
        return jsonify({"status": "error", "message": "Prompt is required."}), 400

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return jsonify({"status": "success", "insight": response.text})
    except Exception as e:
        logging.error(f"Gemini API error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)