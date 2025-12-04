import os

from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

init(autoreset=True)


def get_order_book_depth(symbol: str = "XRPUSDT", limit: int = 5):
    print(
        Fore.MAGENTA
        + f"\n# Unveiling the top {limit} bids and asks for {symbol} (Linear Perpetual)...\n"
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
            + f"  # Fetching order book for {symbol} with limit {limit}..."
            + Style.RESET_ALL,
        )

        # Fetch order book data for linear perpetual futures
        # category: 'linear' for linear perpetual, 'spot' for spot, etc.
        response = session.get_orderbook(category="linear", symbol=symbol, limit=limit)

        if response and response["retCode"] == 0:
            orderbook = response["result"]
            if orderbook:
                print(Fore.GREEN + f"  # Order Book for {symbol}:" + Style.RESET_ALL)
                print(Fore.WHITE + "  Bids (Buy Orders):" + Style.RESET_ALL)
                for bid in orderbook["bids"]:
                    print(
                        Fore.GREEN
                        + f"    Price: {bid[0]}, Quantity: {bid[1]}"
                        + Style.RESET_ALL,
                    )

                print(Fore.WHITE + "  Asks (Sell Orders):" + Style.RESET_ALL)
                for ask in orderbook["asks"]:
                    print(
                        Fore.RED
                        + f"    Price: {ask[0]}, Quantity: {ask[1]}"
                        + Style.RESET_ALL,
                    )
            else:
                print(
                    Fore.YELLOW
                    + f"  # No order book data found for {symbol}."
                    + Style.RESET_ALL,
                )
        else:
            print(
                Fore.RED + "  # Failed to retrieve order book data." + Style.RESET_ALL,
            )
            print(Fore.RED + f"  # Response: {response}" + Style.RESET_ALL)

    except Exception as e:
        print(Fore.RED + f"  # A disturbance in the ether: {e}" + Style.RESET_ALL)
        print(
            Fore.YELLOW
            + "  # Ensure your network connection is stable and API keys are valid."
            + Style.RESET_ALL,
        )

    print(
        Fore.MAGENTA + "\n# The market's depths have been revealed!\n" + Style.RESET_ALL,
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

    get_order_book_depth("XRPUSDT", 5)
