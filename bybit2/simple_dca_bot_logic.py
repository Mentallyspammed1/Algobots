import os

from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

init(autoreset=True)


def simple_dca_bot_logic(
    symbol: str = "BTCUSDT", amount_usdt: float = 10.0, interval_hours: int = 24,
):
    print(
        Fore.MAGENTA
        + f"\n# Outlining the logic for a simple Dollar-Cost Averaging (DCA) bot for {symbol}...\n"
        + Style.RESET_ALL,
    )
    print(
        Fore.MAGENTA
        + f"# This bot aims to buy {amount_usdt} USDT worth of {symbol} every {interval_hours} hours.\n"
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
            + "  # Bybit HTTP session initialized for DCA bot logic."
            + Style.RESET_ALL,
        )

        print(Fore.WHITE + "\n  ## DCA Bot Logic Outline:" + Style.RESET_ALL)
        print(Fore.BLUE + "  1. **Initialization:**" + Style.RESET_ALL)
        print(
            Fore.WHITE + "     - Load API keys and set testnet mode." + Style.RESET_ALL,
        )
        print(Fore.WHITE + "     - Initialize Pybit HTTP session." + Style.RESET_ALL)

        print(Fore.BLUE + "  2. **Main Loop (Scheduled Execution):**" + Style.RESET_ALL)
        print(
            Fore.WHITE
            + f"     - This script would typically be scheduled to run every {interval_hours} hours (e.g., using cron in Termux)."
            + Style.RESET_ALL,
        )
        print(
            Fore.WHITE
            + "     - Inside the loop, perform the following steps:"
            + Style.RESET_ALL,
        )

        print(Fore.BLUE + "  3. **Fetch Current Price:**" + Style.RESET_ALL)
        print(
            Fore.WHITE
            + f"     - Get the current market price of {symbol} (Spot)."
            + Style.RESET_ALL,
        )
        print(
            Fore.GREEN
            + '       Example: `ticker = session.get_tickers(category="spot", symbol="{symbol}")`'
            + Style.RESET_ALL,
        )
        print(
            Fore.WHITE
            + "     - Extract `lastPrice` from the response."
            + Style.RESET_ALL,
        )

        print(Fore.BLUE + "  4. **Calculate Quantity to Buy:**" + Style.RESET_ALL)
        print(
            Fore.WHITE
            + f"     - `qty_to_buy = {amount_usdt} / current_price`"
            + Style.RESET_ALL,
        )
        print(
            Fore.WHITE
            + "     - **Important:** Account for minimum order quantity and price precision for the symbol."
            + Style.RESET_ALL,
        )
        print(
            Fore.WHITE
            + "       You'd need to fetch instrument info to get `lotSizeFilter.minOrderQty` and `priceFilter.tickSize`."
            + Style.RESET_ALL,
        )

        print(Fore.BLUE + "  5. **Place Market Buy Order:**" + Style.RESET_ALL)
        print(
            Fore.WHITE
            + f"     - Place a market buy order for `qty_to_to_buy` of {symbol}."
            + Style.RESET_ALL,
        )
        print(
            Fore.GREEN
            + '       Example: `order = session.place_order(category="spot", symbol="{symbol}", side="Buy", orderType="Market", qty=str(qty_to_buy))`'
            + Style.RESET_ALL,
        )

        print(Fore.BLUE + "  6. **Error Handling & Logging:**" + Style.RESET_ALL)
        print(
            Fore.WHITE
            + "     - **Network Issues/API Errors:** Implement `try-except` blocks for all API calls."
            + Style.RESET_ALL,
        )
        print(
            Fore.WHITE
            + "       - Log errors with timestamps (e.g., to a file or Termux notification)."
            + Style.RESET_ALL,
        )
        print(
            Fore.WHITE
            + "       - Implement retry mechanisms with exponential backoff for transient errors."
            + Style.RESET_ALL,
        )
        print(
            Fore.WHITE
            + "     - **Insufficient Balance:** Check account balance before placing an order."
            + Style.RESET_ALL,
        )
        print(
            Fore.WHITE
            + "       - Log a warning and skip the order if funds are insufficient."
            + Style.RESET_ALL,
        )
        print(
            Fore.WHITE
            + "     - **Order Placement Failure:** Check `retCode` and `retMsg` from Bybit's response."
            + Style.RESET_ALL,
        )
        print(Fore.WHITE + "       - Log details of failed orders." + Style.RESET_ALL)
        print(
            Fore.WHITE
            + "     - **Rate Limits:** Be aware of Bybit's rate limits. If making many calls, implement delays."
            + Style.RESET_ALL,
        )

        print(Fore.BLUE + "  7. **Confirmation & Logging:**" + Style.RESET_ALL)
        print(
            Fore.WHITE
            + "     - After placing an order, log the order ID, quantity, and actual executed price."
            + Style.RESET_ALL,
        )
        print(
            Fore.WHITE
            + "     - Confirm order status (e.g., by fetching order details after a short delay)."
            + Style.RESET_ALL,
        )

        print(
            Fore.YELLOW
            + "\n  # Example Pseudo-code for the main loop:"
            + Style.RESET_ALL,
        )
        print(Fore.WHITE + "  ```python" + Style.RESET_ALL)
        print(Fore.WHITE + "  def run_dca_cycle():" + Style.RESET_ALL)
        print(Fore.WHITE + "      try:" + Style.RESET_ALL)
        print(Fore.WHITE + "          # 1. Fetch current price" + Style.RESET_ALL)
        print(
            Fore.WHITE
            + "          # 2. Calculate qty_to_buy (with precision handling)"
            + Style.RESET_ALL,
        )
        print(Fore.WHITE + "          # 3. Check balance" + Style.RESET_ALL)
        print(Fore.WHITE + "          # 4. Place order" + Style.RESET_ALL)
        print(Fore.WHITE + "          # 5. Log success/failure" + Style.RESET_ALL)
        print(Fore.WHITE + "      except Exception as e:" + Style.RESET_ALL)
        print(Fore.WHITE + "          # Log error" + Style.RESET_ALL)
        print(Fore.WHITE + "  " + Style.RESET_ALL)
        print(Fore.WHITE + '  if __name__ == "__main__":' + Style.RESET_ALL)
        print(Fore.WHITE + "      run_dca_cycle()" + Style.RESET_ALL)
        print(Fore.WHITE + "  ```" + Style.RESET_ALL)

        print(
            Fore.YELLOW
            + "\n  # To automate this, you would set up a cron job in Termux to execute `python your_dca_script.py`"
            + Style.RESET_ALL,
        )
        print(
            Fore.YELLOW
            + f"  # every {interval_hours} hours. (See 'Scheduling with Cron' request for details)."
            + Style.RESET_ALL,
        )

    except Exception as e:
        print(
            Fore.RED
            + f"  # A disturbance in the ether during setup: {e}"
            + Style.RESET_ALL,
        )
        print(
            Fore.YELLOW
            + "  # Ensure your network connection is stable and API keys are valid."
            + Style.RESET_ALL,
        )

    print(
        Fore.MAGENTA
        + "\n# The DCA bot logic has been outlined. May your investments be ever growing!\n"
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

    simple_dca_bot_logic("BTCUSDT", 10.0, 24)
