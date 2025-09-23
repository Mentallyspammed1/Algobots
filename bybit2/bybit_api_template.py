import os

from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

init(autoreset=True)

def bybit_api_template():
    print(Fore.MAGENTA + "\n# Forging a Basic Bybit API Connection Template...\n" + Style.RESET_ALL)

    # Load environment variables from .env file
    load_dotenv()

    # Retrieve API keys from environment variables
    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')

    # Determine if using testnet based on an environment variable or default to True
    # It's crucial to use testnet for development!
    testnet_mode = os.getenv('BYBIT_TESTNET', 'True').lower() == 'true'

    if not api_key or not api_secret:
        print(Fore.RED + "  # ERROR: BYBIT_API_KEY or BYBIT_API_SECRET not found in environment variables or .env file." + Style.RESET_ALL)
        print(Fore.YELLOW + "  # Please set them up as explained in the API Key Management guide." + Style.RESET_ALL)
        return

    print(Fore.CYAN + "  # Initializing Bybit HTTP session..." + Style.RESET_ALL)
    print(Fore.WHITE + f"  # Testnet Mode: {testnet_mode}" + Style.RESET_ALL)

    try:
        session = HTTP(
            testnet=testnet_mode,
            api_key=api_key,
            api_secret=api_secret
        )
        print(Fore.GREEN + "  # Bybit HTTP session initialized successfully!" + Style.RESET_ALL)
        print(Fore.WHITE + "  # You can now use the 'session' object to make API calls." + Style.RESET_ALL)

        # Example: Get server time to verify connection
        print(Fore.CYAN + "\n  # Attempting to fetch server time to verify connection..." + Style.RESET_ALL)
        server_time_response = session.get_server_time()

        if server_time_response and server_time_response['retCode'] == 0:
            time_ms = server_time_response['result']['timeNano'] // 1_000_000 # Convert nanoseconds to milliseconds
            print(Fore.GREEN + f"  # Successfully connected! Current Bybit Server Time (ms): {time_ms}" + Style.RESET_ALL)
        else:
            print(Fore.RED + "  # Failed to retrieve server time." + Style.RESET_ALL)
            print(Fore.RED + f"  # Response: {server_time_response}" + Style.RESET_ALL)

    except Exception as e:
        print(Fore.RED + f"  # An error occurred during session initialization or API call: {e}" + Style.RESET_ALL)
        print(Fore.YELLOW + "  # Ensure your API keys are correct and have the necessary permissions." + Style.RESET_ALL)
        print(Fore.YELLOW + "  # Also, check your network connection." + Style.RESET_ALL)

    print(Fore.MAGENTA + "\n# The basic Bybit API connection template is ready for your enchantments!\n" + Style.RESET_ALL)

if __name__ == "__main__":
    # Create a dummy .env file for demonstration if it doesn't exist
    env_file_path = '.env'
    if not os.path.exists(env_file_path):
        with open(env_file_path, 'w') as f:
            f.write('BYBIT_API_KEY=YOUR_API_KEY_HERE\n')
            f.write('BYBIT_API_SECRET=YOUR_API_SECRET_HERE\n')
            f.write('BYBIT_TESTNET=True\n') # Set to True for testnet, False for mainnet
        print(Fore.YELLOW + f"  # A '.env' file has been created at {env_file_path}." + Style.RESET_ALL)
        print(Fore.YELLOW + "  # Please edit it with your actual Bybit API Key and Secret." + Style.RESET_ALL)
        print(Fore.YELLOW + "  # Remember to use Testnet keys for testing!" + Style.RESET_ALL)

    bybit_api_template()
