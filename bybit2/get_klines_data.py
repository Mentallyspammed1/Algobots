import os

from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

init(autoreset=True)


def get_klines_data(symbol: str = "SOLUSDT", interval: str = "60", limit: int = 100):
    print(
        Fore.MAGENTA
        + f"\n# Conjuring the last {limit} {interval}-minute Klines for {symbol} (Linear Perpetual)...\n"
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
            + f"  # Fetching Klines for {symbol} with interval {interval} and limit {limit}..."
            + Style.RESET_ALL
        )

        # Fetch klines data for linear perpetual futures
        # category: 'linear' for linear perpetual, 'spot' for spot, etc.
        # interval: '1', '3', '5', '15', '30', '60', '120', '240', '360', '720', 'D', 'W', 'M'
        response = session.get_kline(
            category="linear", symbol=symbol, interval=interval, limit=limit
        )

        if response and response["retCode"] == 0:
            klines = response["result"]["list"]
            if klines:
                print(
                    Fore.GREEN
                    + f"  # Successfully retrieved {len(klines)} Klines for {symbol}:"
                    + Style.RESET_ALL
                )
                # Klines are returned in reverse chronological order (newest first)
                # Each kline is [timestamp, open, high, low, close, volume, turnover]
                for kline in reversed(klines):  # Print in chronological order
                    print(
                        Fore.WHITE
                        + f"    Timestamp: {kline[0]}, Open: {kline[1]}, High: {kline[2]}, Low: {kline[3]}, Close: {kline[4]}, Volume: {kline[5]}"
                        + Style.RESET_ALL
                    )
            else:
                print(
                    Fore.YELLOW
                    + f"  # No Klines data found for {symbol} with interval {interval}."
                    + Style.RESET_ALL
                )
        else:
            print(Fore.RED + "  # Failed to retrieve Klines data." + Style.RESET_ALL)
            print(Fore.RED + f"  # Response: {response}" + Style.RESET_ALL)

    except Exception as e:
        print(Fore.RED + f"  # A disturbance in the ether: {e}" + Style.RESET_ALL)
        print(
            Fore.YELLOW
            + "  # Ensure your network connection is stable and API keys are valid."
            + Style.RESET_ALL
        )

    print(
        Fore.MAGENTA + "\n# The Klines have revealed their secrets!\n" + Style.RESET_ALL
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

    get_klines_data("SOLUSDT", "60", 100)
