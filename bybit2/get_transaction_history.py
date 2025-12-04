import os

from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

init(autoreset=True)


def get_transaction_history(limit: int = 10):
    print(
        Fore.MAGENTA
        + f"\n# Consulting the ancient ledgers to retrieve your last {limit} transaction history records...\n"
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
            + f"  # Requesting last {limit} transaction logs for Unified Account..."
            + Style.RESET_ALL,
        )

        # Fetch transaction logs for Unified Account
        # category: 'unified' for Unified Trading Account
        # type: Optional, e.g., 'DEPOSIT', 'WITHDRAW', 'TRANSFER', 'TRADE', etc.
        # limit: Number of records to retrieve
        response = session.get_transaction_log(accountType="UNIFIED", limit=limit)

        if response and response["retCode"] == 0:
            transactions = response["result"]["list"]
            if transactions:
                print(
                    Fore.GREEN
                    + f"  # Last {len(transactions)} Transaction History Records:"
                    + Style.RESET_ALL,
                )
                for tx in transactions:
                    print(
                        Fore.WHITE
                        + f"    Time: {tx.get('createdTime')}, Type: {tx.get('type')}, "
                        f"Coin: {tx.get('coin')}, Amount: {tx.get('amount')}, "
                        f"Tx ID: {tx.get('txID')}" + Style.RESET_ALL,
                    )
            else:
                print(
                    Fore.YELLOW
                    + "  # No transaction history records found for your Unified Account."
                    + Style.RESET_ALL,
                )
        else:
            print(
                Fore.RED
                + "  # Failed to retrieve transaction history."
                + Style.RESET_ALL,
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
        Fore.MAGENTA
        + "\n# The transaction history has been unveiled!\n"
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

    get_transaction_history(10)
