import os

from colorama import Fore
from colorama import Style
from colorama import init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

init(autoreset=True)


def get_specific_symbol_open_orders(symbol: str = "BTCUSDT", category: str = "linear"):
    print(
        Fore.MAGENTA
        + f"\n# Unveiling active open orders for {symbol} on Bybit v5 {category.capitalize()} Perpetual Futures...\n"
        + Style.RESET_ALL
    )

    load_dotenv()
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    testnet_mode = os.getenv("BYBIT_TESTNET", "True").lower() == "true"

    if not api_key or not api_secret:
        print(
            Fore.RED
            + "  # ERROR: BYBIT_API_KEY or BYBIT_API_SECRET not found."
            + Style.RESET_ALL
        )
        print(
            Fore.YELLOW
            + "  # Please ensure your .env file is correctly configured."
            + Style.RESET_ALL
        )
        return

    try:
        session = HTTP(testnet=testnet_mode, api_key=api_key, api_secret=api_secret)
        print(
            Fore.CYAN
            + f"  # Requesting open orders for {symbol} in category {category}..."
            + Style.RESET_ALL
        )

        response = session.get_open_orders(category=category, symbol=symbol)

        if response and response["retCode"] == 0:
            open_orders = response["result"]["list"]
            if open_orders:
                print(
                    Fore.GREEN
                    + f"  # Active Open Orders for {symbol}:"
                    + Style.RESET_ALL
                )
                for order in open_orders:
                    print(
                        Fore.WHITE
                        + f"    Order ID: {order.get('orderId')}, Side: {order.get('side')}, "
                        f"Order Type: {order.get('orderType')}, Price: {order.get('price')}, "
                        f"Qty: {order.get('qty')}, Status: {order.get('orderStatus')}"
                        + Style.RESET_ALL
                    )
            else:
                print(
                    Fore.YELLOW
                    + f"  # No active open orders found for {symbol} in category {category}."
                    + Style.RESET_ALL
                )
        else:
            print(Fore.RED + "  # Failed to retrieve open orders." + Style.RESET_ALL)
            print(Fore.RED + f"  # Response: {response}" + Style.RESET_ALL)

    except Exception as e:
        print(Fore.RED + f"  # A disturbance in the ether: {e}" + Style.RESET_ALL)
        print(
            Fore.YELLOW
            + "  # Ensure your network connection is stable and API keys are valid."
            + Style.RESET_ALL
        )

    print(
        Fore.MAGENTA
        + "\n# The specific symbol's open orders have been revealed!\n"
        + Style.RESET_ALL
    )


if __name__ == "__main__":
    # Ensure a .env file exists for demonstration
    env_file_path = ".env"
    if not os.path.exists(env_file_path):
        with open(env_file_path, "w") as f:
            f.write("BYBIT_API_KEY=YOUR_API_KEY_HERE\n")
            f.write("BYBIT_API_SECRET=YOUR_API_SECRET_HERE\n")
            f.write(
                "BYBIT_TESTNET=True\n"
            )  # Set to True for testnet, False for mainnet
        print(
            Fore.YELLOW
            + f"  # A '.env' file has been created at {env_file_path}."
            + Style.RESET_ALL
        )
        print(
            Fore.YELLOW
            + "  # Please edit it with your actual Bybit API Key and Secret."
            + Style.RESET_ALL
        )
        print(
            Fore.YELLOW
            + "  # Remember to use Testnet keys for testing!"
            + Style.RESET_ALL
        )

    get_specific_symbol_open_orders("BTCUSDT", "linear")
