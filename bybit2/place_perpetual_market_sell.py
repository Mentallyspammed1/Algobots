import os

from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

init(autoreset=True)

def place_perpetual_market_sell(symbol: str = 'BTCUSDT', qty: str = '0.005'):
    print(Fore.MAGENTA + f"\n# Initiating a market sell order for {qty} {symbol} on Bybit v5 Linear Perpetual Futures...\n" + Style.RESET_ALL)

    load_dotenv()
    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')
    testnet_mode = os.getenv('BYBIT_TESTNET', 'True').lower() == 'true'

    if not api_key or not api_secret:
        print(Fore.RED + "  # ERROR: BYBIT_API_KEY or BYBIT_API_SECRET not found." + Style.RESET_ALL)
        print(Fore.YELLOW + "  # Please ensure your .env file is correctly configured." + Style.RESET_ALL)
        return

    try:
        session = HTTP(
            testnet=testnet_mode,
            api_key=api_key,
            api_secret=api_secret
        )
        print(Fore.CYAN + f"  # Attempting to place a market sell order for {qty} {symbol}..." + Style.RESET_ALL)

        # Place a market order
        # category: 'linear' for linear perpetual futures
        # symbol: Trading pair, e.g., 'BTCUSDT'
        # side: 'Buy' or 'Sell'
        # orderType: 'Market' or 'Limit'
        # qty: Quantity to buy/sell
        response = session.place_order(
            category="linear",
            symbol=symbol,
            side="Sell",
            orderType="Market",
            qty=qty
        )

        if response and response['retCode'] == 0:
            order_info = response['result']
            print(Fore.GREEN + "  # Market sell order placed successfully!" + Style.RESET_ALL)
            print(Fore.GREEN + f"    Order ID: {order_info.get('orderId')}" + Style.RESET_ALL)
            print(Fore.GREEN + f"    Order Link ID: {order_info.get('orderLinkId')}" + Style.RESET_ALL)
        else:
            print(Fore.RED + "  # Failed to place market sell order." + Style.RESET_ALL)
            print(Fore.RED + f"  # Response: {response}" + Style.RESET_ALL)
            if response and 'retMsg' in response:
                print(Fore.RED + f"  # Error Message: {response['retMsg']}" + Style.RESET_ALL)

    except Exception as e:
        print(Fore.RED + f"  # A disturbance in the ether: {e}" + Style.RESET_ALL)
        print(Fore.YELLOW + "  # Ensure your network connection is stable, API keys are valid, and you have sufficient balance." + Style.RESET_ALL)

    print(Fore.MAGENTA + "\n# The market sell incantation is complete!\n" + Style.RESET_ALL)

if __name__ == "__main__":
    # Ensure a .env file exists for demonstration
    env_file_path = '.env'
    if not os.path.exists(env_file_path):
        with open(env_file_path, 'w') as f:
            f.write('BYBIT_API_KEY=YOUR_API_KEY_HERE\n')
            f.write('BYBIT_API_SECRET=YOUR_API_SECRET_HERE\n')
            f.write('BYBIT_TESTNET=True\n') # Set to True for testnet, False for mainnet
        print(Fore.YELLOW + f"  # A '.env' file has been created at {env_file_path}." + Style.RESET_ALL)
        print(Fore.YELLOW + "  # Please edit it with your actual Bybit API Key and Secret." + Style.RESET_ALL)
        print(Fore.YELLOW + "  # Remember to use Testnet keys for testing!" + Style.RESET_ALL)

    place_perpetual_market_sell('BTCUSDT', '0.005')
