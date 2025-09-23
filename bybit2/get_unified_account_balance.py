import os

from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

init(autoreset=True)

def get_unified_account_balance(coin: str = 'USDT'):
    print(Fore.MAGENTA + "\n# Scrying the depths of your Bybit v5 Unified Account for {coin} balance...\n" + Style.RESET_ALL)

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
        print(Fore.CYAN + f"  # Requesting account information for {coin}..." + Style.RESET_ALL)

        # Fetch wallet balance for Unified Account
        # accountType: 'UNIFIED' for Unified Trading Account
        response = session.get_wallet_balance(accountType="UNIFIED", coin=coin)

        if response and response['retCode'] == 0:
            if response['result'] and response['result']['list']:
                coin_info = None
                for account in response['result']['list']:
                    for c in account['coins']:
                        if c['coin'] == coin:
                            coin_info = c
                            break
                    if coin_info:
                        break

                if coin_info:
                    available_balance = coin_info['availableToWithdraw']
                    total_balance = coin_info['walletBalance']
                    print(Fore.GREEN + f"  # {coin} Balance in Unified Account:" + Style.RESET_ALL)
                    print(Fore.GREEN + f"    Available: {available_balance}" + Style.RESET_ALL)
                    print(Fore.GREEN + f"    Total: {total_balance}" + Style.RESET_ALL)
                else:
                    print(Fore.YELLOW + f"  # {coin} balance information not found in Unified Account." + Style.RESET_ALL)
            else:
                print(Fore.YELLOW + "  # No account information found for Unified Account." + Style.RESET_ALL)
        else:
            print(Fore.RED + "  # Failed to retrieve account balance." + Style.RESET_ALL)
            print(Fore.RED + f"  # Response: {response}" + Style.RESET_ALL)

    except Exception as e:
        print(Fore.RED + f"  # A disturbance in the ether: {e}" + Style.RESET_ALL)
        print(Fore.YELLOW + "  # Ensure your network connection is stable and API keys are valid." + Style.RESET_ALL)

    print(Fore.MAGENTA + "\n# Your Unified Account balance has been revealed!\n" + Style.RESET_ALL)

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

    get_unified_account_balance('USDT')
