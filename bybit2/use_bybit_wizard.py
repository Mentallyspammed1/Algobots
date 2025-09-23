import json
import os

from bybit_v5_wizard import BybitV5Wizard
from colorama import Fore, Style, init

init(autoreset=True)

def main():
    print(Fore.MAGENTA + "\n# Initiating the grand integration ritual with BybitV5Wizard...\n" + Style.RESET_ALL)

    # Ensure a config file exists for demonstration
    config_file_path = '/data/data/com.termux/files/home/.bybit_config'
    if not os.path.exists(config_file_path):
        with open(config_file_path, 'w') as f:
            json.dump({
                "api_key": "YOUR_API_KEY_HERE",
                "api_secret": "YOUR_API_SECRET_HERE",
                "testnet": True
            }, f, indent=4)
        print(Fore.YELLOW + f"  # A dummy config file has been created at {config_file_path}." + Style.RESET_ALL)
        print(Fore.YELLOW + "  # Please edit it with your actual Bybit API Key and Secret." + Style.RESET_ALL)
        print(Fore.YELLOW + "  # Remember to use Testnet keys for testing!" + Style.RESET_ALL)
        return

    try:
        # Awaken the BybitV5Wizard
        wizard = BybitV5Wizard(config_path=config_file_path)
        print(Fore.GREEN + "  # BybitV5Wizard successfully awakened!" + Style.RESET_ALL)

        # --- Demonstrate Market Data Retrieval ---
        print(Fore.CYAN + "\n  ## Fetching BTCUSDT Spot Ticker..." + Style.RESET_ALL)
        tickers = wizard.get_tickers(category="spot", symbol="BTCUSDT")
        if tickers and tickers.get('list'):
            btc_price = tickers['list'][0]['lastPrice']
            print(Fore.GREEN + f"    Current BTCUSDT Spot Price: {btc_price}" + Style.RESET_ALL)
        else:
            print(Fore.RED + "    Failed to fetch BTCUSDT Spot price." + Style.RESET_ALL)

        print(Fore.CYAN + "\n  ## Fetching ETHUSDT Linear Perpetual Klines (last 5 1-hour candles)..." + Style.RESET_ALL)
        klines = wizard.get_kline(category="linear", symbol="ETHUSDT", interval="60", limit=5)
        if klines and klines.get('list'):
            print(Fore.GREEN + "    ETHUSDT Klines:" + Style.RESET_ALL)
            for kline in reversed(klines['list']):
                print(Fore.WHITE + f"      Time: {kline[0]}, Open: {kline[1]}, Close: {kline[4]}" + Style.RESET_ALL)
        else:
            print(Fore.RED + "    Failed to fetch ETHUSDT Klines." + Style.RESET_ALL)

        # --- Demonstrate Account Management ---
        print(Fore.CYAN + "\n  ## Fetching Unified Account Balance..." + Style.RESET_ALL)
        balance = wizard.get_account_balance(account_type="UNIFIED")
        if balance and balance.get('list'):
            for acc in balance['list']:
                for coin_info in acc['coins']:
                    if coin_info['coin'] == "USDT":
                        print(Fore.GREEN + f"    USDT Available Balance: {coin_info['availableToWithdraw']}" + Style.RESET_ALL)
                        print(Fore.GREEN + f"    USDT Total Balance: {coin_info['walletBalance']}" + Style.RESET_ALL)
                        break
        else:
            print(Fore.RED + "    Failed to fetch account balance." + Style.RESET_ALL)

        # --- Demonstrate Trading Operation (Example: Place a small market buy order on testnet) ---
        # WARNING: This will attempt to place a real order on testnet if your API keys are valid.
        # Ensure you understand the implications.
        print(Fore.CYAN + "\n  ## Attempting to place a small market buy order for BTCUSDT (Testnet)..." + Style.RESET_ALL)
        print(Fore.YELLOW + "    (This will only work if your API keys are configured for testnet and have trading permissions)" + Style.RESET_ALL)

        # You might want to comment out the following lines if you don't want to place an order.
        # order_result = wizard.place_market_order(symbol="BTCUSDT", side="Buy", qty=0.0001, category="spot")
        # if order_result:
        #     print(Fore.GREEN + f"    Market buy order placed! Order ID: {order_result.get('orderId')}" + Style.RESET_ALL)
        # else:
        #     print(Fore.RED + "    Failed to place market buy order." + Style.RESET_ALL)

        print(Fore.MAGENTA + "\n# Integration ritual complete. The BybitV5Wizard stands ready for your commands!\n" + Style.RESET_ALL)

    except Exception as e:
        print(Fore.RED + f"# A critical error occurred during the integration ritual: {e}" + Style.RESET_ALL)
        print(Fore.YELLOW + "# Please ensure your .bybit_config file is correctly set up and dependencies are installed." + Style.RESET_ALL)

if __name__ == "__main__":
    main()
