import os

from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

init(autoreset=True)


def cancel_specific_order(order_id: str, symbol: str, category: str = "linear"):
    print(
        Fore.MAGENTA
        + f"\n# Attempting to cancel order {order_id} for {symbol} in category {category}...\n"
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
            + f"  # Sending cancellation request for Order ID: {order_id}, Symbol: {symbol}, Category: {category}..."
            + Style.RESET_ALL,
        )

        # Cancel a specific order
        # category: 'linear', 'spot', 'inverse', 'option'
        # symbol: Trading pair
        # orderId: The ID of the order to cancel
        response = session.cancel_order(
            category=category, symbol=symbol, orderId=order_id,
        )

        if response and response["retCode"] == 0:
            print(
                Fore.GREEN
                + f"  # Order {order_id} for {symbol} cancelled successfully!"
                + Style.RESET_ALL,
            )
            print(Fore.GREEN + f"    Response: {response['result']}" + Style.RESET_ALL)
        else:
            print(Fore.RED + "  # Failed to cancel order." + Style.RESET_ALL)
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
            + "  # Ensure your network connection is stable, API keys are valid, and the order ID/symbol/category are correct."
            + Style.RESET_ALL,
        )

    print(
        Fore.MAGENTA
        + "\n# The order cancellation incantation is complete!\n"
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

    # IMPORTANT: Replace with a real order ID and symbol from your testnet account!
    # You can get an order ID by placing a limit order and then fetching open orders.
    dummy_order_id = "YOUR_ORDER_ID_HERE"  # e.g., "1234567890123456789"
    dummy_symbol = "BTCUSDT"
    dummy_category = "linear"  # or "spot", "inverse", "option"

    if dummy_order_id == "YOUR_ORDER_ID_HERE":
        print(
            Fore.YELLOW
            + "\n  # WARNING: Please replace 'YOUR_ORDER_ID_HERE' with an actual order ID from your Bybit testnet account."
            + Style.RESET_ALL,
        )
        print(
            Fore.YELLOW
            + "  # This script will not function correctly without a valid order ID."
            + Style.RESET_ALL,
        )
    else:
        cancel_specific_order(dummy_order_id, dummy_symbol, dummy_category)
