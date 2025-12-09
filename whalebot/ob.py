import json
import time
import os
import argparse
from typing import Dict, List, Tuple
import websocket
from colorama import init, Fore, Style

init(autoreset=True)

NEON_GREEN = Style.BRIGHT + Fore.GREEN
NEON_RED = Style.BRIGHT + Fore.RED
NEON_CYAN = Style.BRIGHT + Fore.CYAN
NEON_MAGENTA = Style.BRIGHT + Fore.MAGENTA
NEON_YELLOW = Style.BRIGHT + Fore.YELLOW
RESET = Style.RESET_ALL

GLOBAL_SYMBOL = "BTCUSDT"
ORDERBOOK_DEPTH = 10
WEBSOCKET_URL = "wss://stream.bybit.com/v5/public/spot"

order_book: Dict[str, Dict[float, float]] = {
    'bids': {},
    'asks': {}
}

def get_symbol_from_args():
    parser = argparse.ArgumentParser(description=f"Bybit L2 Scalping Terminal. Current time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    parser.add_argument(
        '--symbol',
        type=str,
        default='BTCUSDT',
        help='The trading pair symbol (e.g., BTCUSDT, ETHUSDT). Defaults to BTCUSDT.'
    )
    parser.add_argument(
        '--depth',
        type=int,
        default=10,
        help='The number of levels to display (1 to 1000). Defaults to 10.'
    )
    args = parser.parse_args()
    
    global GLOBAL_SYMBOL, ORDERBOOK_DEPTH
    GLOBAL_SYMBOL = args.symbol.upper()
    ORDERBOOK_DEPTH = max(1, min(args.depth, 1000))
    
    return GLOBAL_SYMBOL

def sort_and_trim_book():
    global order_book
    
    sorted_bids = sorted(order_book['bids'].items(), key=lambda item: item[0], reverse=True)
    order_book['bids'] = dict(sorted_bids)

    sorted_asks = sorted(order_book['asks'].items(), key=lambda item: item[0], reverse=False)
    order_book['asks'] = dict(sorted_asks)

def apply_orderbook_delta(data: Dict):
    op = data.get('type')
    bids_data = data['data'].get('b', [])
    asks_data = data['data'].get('a', [])

    if op == 'snapshot':
        order_book['bids'].clear()
        order_book['asks'].clear()

    for price_str, qty_str in bids_data:
        price = float(price_str)
        qty = float(qty_str)
        if qty > 0:
            order_book['bids'][price] = qty
        else:
            order_book['bids'].pop(price, None) 

    for price_str, qty_str in asks_data:
        price = float(price_str)
        qty = float(qty_str)
        if qty > 0:
            order_book['asks'][price] = qty
        else:
            order_book['asks'].pop(price, None) 
    
    sort_and_trim_book()

def calculate_scalping_metrics(bids: Dict, asks: Dict) -> Tuple[float, float, float, str]:
    if not bids or not asks:
        return 0.0, 0.0, 0.5, f"{NEON_CYAN}Waiting for data...{RESET}"

    best_bid = max(bids.keys())
    best_ask = min(asks.keys())

    spread = best_ask - best_bid
    mid_price = (best_bid + best_ask) / 2.0

    top_bids = sorted(bids.items(), key=lambda item: item[0], reverse=True)[:ORDERBOOK_DEPTH]
    top_asks = sorted(asks.items(), key=lambda item: item[0], reverse=False)[:ORDERBOOK_DEPTH]
    
    total_bid_vol = sum(vol for _, vol in top_bids)
    total_ask_vol = sum(vol for _, vol in top_asks)
    total_liquidity = total_bid_vol + total_ask_vol

    imbalance = 0.5
    if total_liquidity > 0:
        imbalance = total_bid_vol / total_liquidity
    
    if imbalance > 0.55:
        imbalance_trend = f"{NEON_GREEN}BULLISH PRESSURE ↑"
    elif imbalance < 0.45:
        imbalance_trend = f"{NEON_RED}BEARISH PRESSURE ↓"
    else:
        imbalance_trend = f"{NEON_CYAN}BALANCED ↔"
        
    return mid_price, spread, imbalance, imbalance_trend

def render_terminal(bids: Dict, asks: Dict, metrics: Tuple):
    os.system('clear' if os.name == 'posix' else 'cls')

    mid_price, spread, imbalance, imbalance_trend = metrics
    
    header_width = 85
    header = f"{NEON_MAGENTA}{Style.BRIGHT}{'=' * header_width}{RESET}\n"
    header += f"{NEON_CYAN}{Style.BRIGHT}  BYBIT L2 SCALPING TERMINAL | {GLOBAL_SYMBOL} | DEPTH: {ORDERBOOK_DEPTH} LEVELS{RESET}\n"
    header += f"{NEON_MAGENTA}{'=' * header_width}{RESET}\n"
    print(header)

    metrics_panel = ""
    price_format = ",.2f" if mid_price > 1000 else ",.4f"
    
    metrics_panel += f"{NEON_CYAN}  MID PRICE:{NEON_MAGENTA}{mid_price:{price_format}>20} USD{RESET}\n"
    metrics_panel += f"{NEON_CYAN}  SPREAD:{NEON_MAGENTA}{spread:,.6f}>23}{RESET}\n"
    metrics_panel += f"{NEON_CYAN}  VOLUME IMBALANCE (VI):{NEON_MAGENTA}{imbalance:.4f} {RESET}| {imbalance_trend}{RESET}\n"
    metrics_panel += f"{NEON_MAGENTA}{'-' * header_width}{RESET}\n"
    print(metrics_panel)

    ask_items = list(asks.items())[:ORDERBOOK_DEPTH]
    bid_items = list(bids.items())[:ORDERBOOK_DEPTH]
    
    ask_items += [(0.0, 0.0)] * (ORDERBOOK_DEPTH - len(ask_items))
    bid_items += [(0.0, 0.0)] * (ORDERBOOK_DEPTH - len(bid_items))
    
    print(f"{NEON_YELLOW}{Style.BRIGHT}{'ASK VOLUME (SELL)':<20} | {'PRICE':<20} | {'PRICE':>20} | {'BID VOLUME (BUY)':>20}{RESET}")
    print(f"{NEON_MAGENTA}{'-' * header_width}{RESET}")

    for i in range(ORDERBOOK_DEPTH):
        ask_price, ask_qty = ask_items[i]
        ask_qty_display = f"{ask_qty / 1000:,.2f}K" if ask_qty >= 1000 else f"{ask_qty:,.3f}"
        ask_price_display = f"{ask_price:{price_format}}" if ask_price > 0 else ""
        ask_line = f"{NEON_RED}{ask_qty_display:<20}{RESET} | {NEON_RED}{ask_price_display:<20}{RESET}"

        bid_price, bid_qty = bid_items[i]
        bid_qty_display = f"{bid_qty / 1000:,.2f}K" if bid_qty >= 1000 else f"{bid_qty:,.3f}"
        bid_price_display = f"{bid_price:{price_format}}" if bid_price > 0 else ""
        bid_line = f"{NEON_GREEN}{bid_price_display:>20}{RESET} | {NEON_GREEN}{bid_qty_display:>20}{RESET}"

        print(f"{ask_line} | {bid_line}")

    print(f"{NEON_MAGENTA}{'-' * header_width}{RESET}")
    print(f"{NEON_CYAN}  {time.strftime('%Y-%m-%d %H:%M:%S')} UTC{RESET}")

def on_message(ws, message):
    try:
        data = json.loads(message)
        
        if data.get('topic', '').startswith('orderbook'):
            apply_orderbook_delta(data)
            metrics = calculate_scalping_metrics(order_book['bids'], order_book['asks'])
            render_terminal(order_book['bids'], order_book['asks'], metrics)
            
        elif data.get('op') == 'pong' or data.get('ret_msg') == 'pong':
            pass
            
        elif data.get('success') is False:
            print(f"{NEON_RED}WS ERROR: {data.get('ret_msg')}{RESET}")
            
    except Exception as e:
        print(f"{NEON_RED}ERROR PROCESSING MESSAGE: {e}{RESET}")
        print(message)

def on_error(ws, error):
    print(f"\n{NEON_RED}### ERROR ###{RESET}")
    print(f"{NEON_RED}{error}{RESET}")

def on_close(ws, close_status_code, close_msg):
    print(f"\n{NEON_MAGENTA}### CONNECTION CLOSED ###{RESET}")
    print(f"Status: {close_status_code}, Message: {close_msg}")

def on_open(ws):
    print(f"{NEON_GREEN}### CONNECTION OPENED ###{RESET}")
    print(f"{NEON_CYAN}Subscribing to {GLOBAL_SYMBOL} L2 Order Book...{RESET}")
    
    topic = f"orderbook.1000.{GLOBAL_SYMBOL}" 
    
    subscribe_msg = {
        "op": "subscribe",
        "args": [topic]
    }
    ws.send(json.dumps(subscribe_msg))
    print(f"{NEON_GREEN}Subscription request sent for topic: {topic}.{RESET}")

def on_ping(ws, data):
    ws.send(json.dumps({"op": "pong"}))

if __name__ == "__main__":
    get_symbol_from_args()
    
    while True:
        try:
            ws_app = websocket.WebSocketApp(
                WEBSOCKET_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_ping=on_ping
            )
            
            print(f"{NEON_CYAN}Connecting to Bybit WebSocket URL: {WEBSOCKET_URL} for {GLOBAL_SYMBOL}...{RESET}")
            ws_app.run_forever(ping_interval=30, ping_timeout=10, sslopt={"check_hostname": False})
            
        except KeyboardInterrupt:
            print(f"\n{NEON_MAGENTA}Terminal stopped by user (Ctrl+C). Cleaning up...{RESET}")
            if 'ws_app' in locals():
                ws_app.close()
            break
        except Exception as e:
            print(f"{NEON_RED}A critical error occurred: {e}{RESET}. Retrying connection in 5 seconds...{RESET}")
            time.sleep(5)
