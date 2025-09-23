import os

from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

init(autoreset=True)

def place_linked_tp_sl_order(symbol: str = 'ETHUSDT', position_idx: int = 0, take_profit_price: str = '2100', stop_loss_price: str = '1900', category: str = 'linear'):
    print(Fore.MAGENTA + f"\n# Weaving a linked Take-Profit ({take_profit_price}) and Stop-Loss ({stop_loss_price}) order for {symbol}...\n" + Style.RESET_ALL)

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
        print(Fore.CYAN + f"  # Attempting to set TP/SL for {symbol}..." + Style.RESET_ALL)

        # Place a linked Take-Profit and Stop-Loss order
        # This assumes you already have an open position for the symbol.
        # positionIdx: 0 for one-way mode, 1 for buy side of hedge mode, 2 for sell side of hedge mode
        # takeProfit: Take profit price
        # stopLoss: Stop loss price
        # tpTriggerBy: Trigger price type for TP (e.g., 'MarkPrice', 'LastPrice', 'IndexPrice')
        # slTriggerBy: Trigger price type for SL (e.g., 'MarkPrice', 'LastPrice', 'IndexPrice')
        response = session.set_trading_stop(
            category=category,
            symbol=symbol,
            takeProfit=take_profit_price,
            stopLoss=stop_loss_price,
            tpTriggerBy="MarkPrice", # Common choice, adjust if needed
            slTriggerBy="MarkPrice", # Common choice, adjust if needed
            positionIdx=position_idx
        )

        if response and response['retCode'] == 0:
            print(Fore.GREEN + "  # Linked Take-Profit and Stop-Loss orders placed successfully!" + Style.RESET_ALL)
            print(Fore.GREEN + f"    Response: {response['result']}" + Style.RESET_ALL)
        else:
            print(Fore.RED + "  # Failed to place linked TP/SL orders." + Style.RESET_ALL)
            print(Fore.RED + f"  # Response: {response}" + Style.RESET_ALL)
            if response and 'retMsg' in response:
                print(Fore.RED + f"  # Error Message: {response['retMsg']}" + Style.RESET_ALL)

    except Exception as e:
        print(Fore.RED + f"  # A disturbance in the ether: {e}" + Style.RESET_ALL)
        print(Fore.YELLOW + "  # Ensure your network connection is stable, API keys are valid, and you have an existing position." + Style.RESET_ALL)

    print(Fore.MAGENTA + "\n# The TP/SL incantation is complete!\n" + Style.RESET_ALL)

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

    # IMPORTANT: Ensure you have an open ETHUSDT linear perpetual position on testnet before running this!
    # position_idx: 0 for one-way mode, 1 for buy side of hedge mode, 2 for sell side of hedge mode
    place_linked_tp_sl_order('ETHUSDT', position_idx=0, take_profit_price='2100', stop_loss_price='1900', category='linear')
