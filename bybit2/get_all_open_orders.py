import os

from colorama import Fore
from colorama import Style
from colorama import init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

init(autoreset=True)


def get_all_open_orders():
    print(
        Fore.MAGENTA
        + "\n# Unveiling all active open orders across all symbols on your Bybit v5 Unified Account...\n"
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
        print(Fore.CYAN + "  # Requesting all open orders..." + Style.RESET_ALL)

        # Fetch open orders for all categories (spot, linear, inverse, option)
        # Bybit API requires specifying category for get_open_orders
        # We will iterate through common categories to get all open orders
        categories = ["spot", "linear", "inverse", "option"]
        all_open_orders = []

        for category in categories:
            print(
                Fore.CYAN
                + f"  # Fetching open orders for category: {category}..."
                + Style.RESET_ALL
            )
            response = session.get_open_orders(category=category)

            if response and response["retCode"] == 0:
                if response["result"] and response["result"]["list"]:
                    all_open_orders.extend(response["result"]["list"])
                else:
                    print(
                        Fore.YELLOW
                        + f"  # No open orders found for category: {category}."
                        + Style.RESET_ALL
                    )
            else:
                print(
                    Fore.RED
                    + f"  # Failed to retrieve open orders for category {category}."
                    + Style.RESET_ALL
                )
                print(Fore.RED + f"  # Response: {response}" + Style.RESET_ALL)

        if all_open_orders:
            print(Fore.GREEN + "  # All Active Open Orders:" + Style.RESET_ALL)
            for order in all_open_orders:
                print(
                    Fore.WHITE
                    + f"    Symbol: {order.get('symbol')}, Order ID: {order.get('orderId')}, Side: {order.get('side')}, "
                    f"Order Type: {order.get('orderType')}, Price: {order.get('price')}, Qty: {order.get('qty')}, "
                    f"Status: {order.get('orderStatus')}" + Style.RESET_ALL
                )
        else:
            print(
                Fore.YELLOW
                + "  # No active open orders found across all categories."
                + Style.RESET_ALL
            )

    except Exception as e:
        print(Fore.RED + f"  # A disturbance in the ether: {e}" + Style.RESET_ALL)
        print(
            Fore.YELLOW
            + "  # Ensure your network connection is stable and API keys are valid."
            + Style.RESET_ALL
        )

    print(
        Fore.MAGENTA
        + "\n# The scroll of open orders has been fully revealed!\n"
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

    get_all_open_orders()
