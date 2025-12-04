import os

from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

init(autoreset=True)


def cancel_all_orders_for_symbol(symbol: str = "DOGEUSDT", category: str = "linear"):
    print(
        Fore.MAGENTA
        + f"\n# Initiating the ritual to cancel all open orders for {symbol} in category {category}...\n"
        + Style.RESET_ALL,
    )

    load_dotenv()
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    testnet_mode = os.getenv("BYBIT_TESTNET", "True").lower() == "true"

    if not api_key or not api_secret:
        print(
            Fore.RED
            + "  # ERROR: BYBIT_API_KEY or BYBIT_API_SECRET not found."
            + Style.RESET_ALL,
        )
        print(
            Fore.YELLOW
            + "  # Please ensure your .env file is correctly configured."
            + Style.RESET_ALL,
        )
        return

    try:
        session = HTTP(testnet=testnet_mode, api_key=api_key, api_secret=api_secret)
        print(
            Fore.CYAN
            + f"  # Sending cancellation request for all orders of Symbol: {symbol}, Category: {category}..."
            + Style.RESET_ALL,
        )

        # Cancel all orders for a specific symbol and category
        # category: 'linear', 'spot', 'inverse', 'option'
        # symbol: Trading pair
        response = session.cancel_all_orders(category=category, symbol=symbol)

        if response and response["retCode"] == 0:
            print(
                Fore.GREEN
                + f"  # All open orders for {symbol} cancelled successfully!"
                + Style.RESET_ALL,
            )
            print(Fore.GREEN + f"    Response: {response['result']}" + Style.RESET_ALL)
        else:
            print(Fore.RED + "  # Failed to cancel all orders." + Style.RESET_ALL)
            print(Fore.RED + f"  # Response: {response}" + Style.RESET_ALL)
            if response and "retMsg" in response:
                print(
                    Fore.RED
                    + f"  # Error Message: {response['retMsg']}"
                    + Style.RESET_ALL,
                )

    except Exception as e:
        print(Fore.RED + f"  # A disturbance in the ether: {e}" + Style.RESET_ALL)
        print(
            Fore.YELLOW
            + "  # Ensure your network connection is stable, API keys are valid, and the symbol/category are correct."
            + Style.RESET_ALL,
        )

    print(
        Fore.MAGENTA
        + "\n# The mass order cancellation incantation is complete!\n"
        + Style.RESET_ALL,
    )


if __name__ == "__main__":
    # Ensure a .env file exists for demonstration
    env_file_path = ".env"
    if not os.path.exists(env_file_path):
        with open(env_file_path, "w") as f:
            f.write("BYBIT_API_KEY=YOUR_API_KEY_HERE\n")
            f.write("BYBIT_API_SECRET=YOUR_API_SECRET_HERE\n")
            f.write(
                "BYBIT_TESTNET=True\n",
            )  # Set to True for testnet, False for mainnet
        print(
            Fore.YELLOW
            + f"  # A '.env' file has been created at {env_file_path}."
            + Style.RESET_ALL,
        )
        print(
            Fore.YELLOW
            + "  # Please edit it with your actual Bybit API Key and Secret."
            + Style.RESET_ALL,
        )
        print(
            Fore.YELLOW
            + "  # Remember to use Testnet keys for testing!"
            + Style.RESET_ALL,
        )

    cancel_all_orders_for_symbol("DOGEUSDT", "linear")
