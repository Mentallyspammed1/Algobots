import os

from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

init(autoreset=True)

def get_bybit_server_time():
    print(Fore.MAGENTA + "\n# Consulting the Chronomancer to retrieve Bybit server time...\n" + Style.RESET_ALL)

    load_dotenv()
    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')
    testnet_mode = os.getenv('BYBIT_TESTNET', 'True').lower() == 'true'

    # API keys are not strictly necessary for public endpoints like server time, but including them
    # for consistency with other scripts and in case Bybit changes this in the future.
    # If you only need public endpoints, you can initialize HTTP without keys.
    try:
        session = HTTP(
            testnet=testnet_mode,
            api_key=api_key,
            api_secret=api_secret
        )
        print(Fore.CYAN + "  # Requesting the current server time from Bybit..." + Style.RESET_ALL)

        response = session.get_server_time()

        if response and response['retCode'] == 0:
            # The time is returned in nanoseconds, convert to milliseconds for common use
            time_nano = int(response['result']['timeNano'])
            time_ms = time_nano // 1_000_000
            print(Fore.GREEN + f"  # Current Bybit Server Time (milliseconds): {time_ms}" + Style.RESET_ALL)
            print(Fore.GREEN + f"  # Current Bybit Server Time (nanoseconds): {time_nano}" + Style.RESET_ALL)
            print(Fore.WHITE + "  # You can compare this with your local system time to check for synchronization issues." + Style.RESET_ALL)
        else:
            print(Fore.RED + "  # Failed to retrieve server time." + Style.RESET_ALL)
            print(Fore.RED + f"  # Response: {response}" + Style.RESET_ALL)

    except Exception as e:
        print(Fore.RED + f"  # A temporal anomaly occurred: {e}" + Style.RESET_ALL)
        print(Fore.YELLOW + "  # Ensure your network connection is stable." + Style.RESET_ALL)

    print(Fore.MAGENTA + "\n# The server time has been revealed!\n" + Style.RESET_ALL)

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

    get_bybit_server_time()
