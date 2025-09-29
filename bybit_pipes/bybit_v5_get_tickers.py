import argparse
import json
import os

from colorama import Fore, Style, init
from pybit.unified_trading import HTTP

# Initialize Colorama
init(autoreset=True)


def main():
    """# Fetches ticker information from Bybit V5 API.
    # An incantation to reveal the current pulse of the market.
    """
    parser = argparse.ArgumentParser(
        description=Fore.CYAN + "Fetch Bybit V5 Tickers." + Style.RESET_ALL
    )
    parser.add_argument(
        "--category",
        type=str,
        required=True,
        help="Category: spot, linear, inverse, option",
    )
    parser.add_argument("--symbol", type=str, help="Symbol, e.g., BTCUSDT")
    args = parser.parse_args()

    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")

    if not api_key or not api_secret:
        print(
            Fore.RED
            + "Error: BYBIT_API_KEY and BYBIT_API_SECRET environment variables must be set."
        )
        return

    session = HTTP(
        testnet=False,
        api_key=api_key,
        api_secret=api_secret,
    )

    try:
        print(
            Fore.MAGENTA
            + f"# Summoning ticker data for {args.category.upper()}::{args.symbol or 'All Symbols'}..."
        )

        params = {"category": args.category}
        if args.symbol:
            params["symbol"] = args.symbol

        response = session.get_tickers(**params)

        if response.get("retCode") == 0:
            print(Fore.GREEN + "# Market pulse received successfully.")
            # Pretty print the JSON output
            print(json.dumps(response, indent=4))
        else:
            print(Fore.RED + f"# A disturbance in the ether: {response.get('retMsg')}")
            print(json.dumps(response, indent=4))

    except Exception as e:
        print(Fore.RED + f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
