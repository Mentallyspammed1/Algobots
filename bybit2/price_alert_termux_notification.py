import os
import time

from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

init(autoreset=True)


def price_alert_termux_notification(
    symbol: str = "BTCUSDT",
    upper_threshold: float = 30000.0,
    lower_threshold: float = 29000.0,
    check_interval_seconds: int = 60,
):
    print(
        Fore.MAGENTA
        + f"\n# Setting up a mystical price alert for {symbol} on Bybit v5...\n"
        + Style.RESET_ALL,
    )
    print(
        Fore.MAGENTA
        + f"# Will notify if price goes above {upper_threshold} or below {lower_threshold}.\n"
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
            + "  # Bybit HTTP session initialized for price monitoring."
            + Style.RESET_ALL,
        )
        print(
            Fore.YELLOW
            + "  # Ensure 'termux-api' is installed (`pkg install termux-api`) and Termux has notification permissions."
            + Style.RESET_ALL,
        )

        last_alert_state = None  # To prevent repeated notifications for the same breach

        while True:
            try:
                print(
                    Fore.CYAN
                    + f"\n  # Checking current price of {symbol}..."
                    + Style.RESET_ALL,
                )
                response = session.get_tickers(category="spot", symbol=symbol)

                if response and response["retCode"] == 0:
                    if response["result"] and response["result"]["list"]:
                        current_price = float(
                            response["result"]["list"][0]["lastPrice"],
                        )
                        print(
                            Fore.GREEN
                            + f"    Current {symbol} Price: {current_price}"
                            + Style.RESET_ALL,
                        )

                        if (
                            current_price >= upper_threshold
                            and last_alert_state != "above"
                        ):
                            message = f"{symbol} price ({current_price}) is ABOVE {upper_threshold}!"
                            print(
                                Fore.LIGHTRED_EX
                                + f"  # ALERT: {message}"
                                + Style.RESET_ALL,
                            )
                            os.system(f'termux-toast "{message}"')
                            last_alert_state = "above"
                        elif (
                            current_price <= lower_threshold
                            and last_alert_state != "below"
                        ):
                            message = f"{symbol} price ({current_price}) is BELOW {lower_threshold}!"
                            print(
                                Fore.LIGHTRED_EX
                                + f"  # ALERT: {message}"
                                + Style.RESET_ALL,
                            )
                            os.system(f'termux-toast "{message}"')
                            last_alert_state = "below"
                        elif (
                            lower_threshold < current_price < upper_threshold
                            and last_alert_state is not None
                        ):
                            # Reset alert state if price returns within bounds after an alert
                            print(
                                Fore.WHITE
                                + f"    {symbol} price is within bounds ({lower_threshold}-{upper_threshold})."
                                + Style.RESET_ALL,
                            )
                            last_alert_state = None
                        else:
                            print(
                                Fore.WHITE
                                + f"    {symbol} price is within bounds ({lower_threshold}-{upper_threshold})."
                                + Style.RESET_ALL,
                            )

                    else:
                        print(
                            Fore.YELLOW
                            + f"  # No ticker data found for {symbol}. Retrying..."
                            + Style.RESET_ALL,
                        )
                else:
                    print(
                        Fore.RED
                        + "  # Failed to retrieve ticker information."
                        + Style.RESET_ALL,
                    )
                    print(Fore.RED + f"  # Response: {response}" + Style.RESET_ALL)

            except Exception as e:
                print(
                    Fore.RED
                    + f"  # A temporary disturbance in the ether during price check: {e}"
                    + Style.RESET_ALL,
                )
                print(Fore.YELLOW + "  # Retrying after delay..." + Style.RESET_ALL)

            print(
                Fore.CYAN
                + f"  # Waiting {check_interval_seconds} seconds before next price check..."
                + Style.RESET_ALL,
            )
            time.sleep(check_interval_seconds)

    except Exception as e:
        print(
            Fore.RED
            + f"  # A critical disturbance in the ether during setup: {e}"
            + Style.RESET_ALL,
        )
        print(
            Fore.YELLOW
            + "  # Ensure your network connection is stable and API keys are valid."
            + Style.RESET_ALL,
        )

    print(
        Fore.MAGENTA
        + "\n# The price alert ritual has concluded (or encountered a fatal error)."
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

    # You can modify these parameters as needed
    price_alert_termux_notification("BTCUSDT", 30000.0, 29000.0, 60)
