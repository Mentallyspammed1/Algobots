# bybit_account_helper.py
import logging
import time  # For potential timestamp in error logging
from typing import Any

from pybit.exceptions import (  # Import specific Pybit exceptions
    BybitAPIError,
    BybitRequestError,
)
from pybit.unified_trading import HTTP

# Configure logging for the module
logging.basicConfig(
    level=logging.INFO,  # Changed to INFO for less verbose default output, DEBUG for full details
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


class BybitAccountHelper:
    """A helper class for managing Bybit account-related functionalities
    including wallet balances, asset transfers, profit/loss tracking,
    and fee information via the Unified Trading HTTP API.
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        """Initializes the BybitAccountHelper with API credentials and environment.

        :param api_key: Your Bybit API key.
        :param api_secret: Your Bybit API secret.
        :param testnet: Set to True to connect to the Bybit testnet, False for mainnet.
        """
        if not api_key or not api_secret:
            logger.error("API Key and Secret are required for BybitAccountHelper.")
            raise ValueError("API Key and Secret must be provided.")

        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.session = HTTP(
            testnet=self.testnet, api_key=self.api_key, api_secret=self.api_secret
        )
        logger.info(
            f"BybitAccountHelper initialized for {'testnet' if self.testnet else 'mainnet'}."
        )

    def _make_request(
        self, method: str, endpoint_name: str, **kwargs
    ) -> dict[str, Any] | None:
        """Internal method to make an HTTP request to the Bybit API and handle responses.
        It centralizes error handling and logging for API calls.

        :param method: The name of the method to call on the `self.session` object (e.g., 'get_wallet_balance').
        :param endpoint_name: A descriptive name for the API endpoint, used in logging.
        :param kwargs: Keyword arguments to pass directly to the `pybit` API method.
        :return: The 'result' dictionary from the API response if the call is successful (retCode == 0),
                 otherwise returns None after logging the error.
        """
        full_method_name = f"session.{method}"
        try:
            func = getattr(self.session, method)
            response = func(**kwargs)

            if response and response.get("retCode") == 0:
                logger.debug(
                    f"[{endpoint_name}] Successfully called. Response: {response.get('result')}"
                )
                return response.get("result")
            ret_code = response.get("retCode", "N/A")
            error_msg = response.get("retMsg", "Unknown error")
            logger.error(
                f"[{endpoint_name}] API call failed. Code: {ret_code}, Message: {error_msg}. "
                f"Args: {kwargs}. Full Response: {response}"
            )
            return None
        except (BybitRequestError, BybitAPIError) as e:
            logger.exception(
                f"[{endpoint_name}] Pybit specific error during API call. "
                f"Args: {kwargs}. Error: {e}"
            )
            return None
        except Exception as e:
            logger.exception(
                f"[{endpoint_name}] Unexpected exception during API call. "
                f"Args: {kwargs}. Error: {e}"
            )
            return None

    def get_wallet_balance(
        self, account_type: str = "UNIFIED"
    ) -> dict[str, Any] | None:
        """Retrieves comprehensive wallet balance and risk information for a specified account type.

        :param account_type: The type of account (e.g., "UNIFIED", "CLASSIC", "SPOT").
                             Defaults to "UNIFIED".
        :return: A dictionary containing wallet balance information (e.g., totalEquity, availableToWithdraw)
                 or None on failure. The 'list' key in the result typically contains account details.
        """
        if not isinstance(account_type, str) or not account_type:
            logger.error("Invalid 'account_type' provided for get_wallet_balance.")
            return None
        return self._make_request(
            "get_wallet_balance", "Account Wallet Balance", accountType=account_type
        )

    def get_transferable_amount(self, coin_name: str) -> dict[str, Any] | None:
        """Queries the available amount of a specific coin that can be transferred.

        :param coin_name: The name of the coin (e.g., "USDT", "BTC").
        :return: A dictionary containing transferable amount information (e.g., 'transferAbleAmount')
                 or None on failure.
        """
        if not isinstance(coin_name, str) or not coin_name:
            logger.error("Invalid 'coin_name' provided for get_transferable_amount.")
            return None
        return self._make_request(
            "get_transferable_amount", "Transferable Amount", coinName=coin_name
        )

    def get_coins_balance(
        self, member_id: str, account_type: str = "UNIFIED"
    ) -> dict[str, Any] | None:
        """Retrieves all coin balances across account types for a specific member.
        Note: `member_id` is typically your Bybit UID.

        :param member_id: The unique identifier of the member (your UID).
        :param account_type: The type of account (e.g., "UNIFIED", "CLASSIC"). Defaults to "UNIFIED".
        :return: A dictionary containing a list of coin balances or None on failure.
        """
        if not isinstance(member_id, str) or not member_id:
            logger.error("Invalid 'member_id' provided for get_coins_balance.")
            return None
        if not isinstance(account_type, str) or not account_type:
            logger.error("Invalid 'account_type' provided for get_coins_balance.")
            return None
        return self._make_request(
            "get_coins_balance",
            "All Coins Balance",
            memberId=member_id,
            accountType=account_type,
        )

    def get_coin_balance(
        self, member_id: str, coin: str, account_type: str = "UNIFIED"
    ) -> dict[str, Any] | None:
        """Queries the balance of a specific coin for a specific member and account type.
        Note: `member_id` is typically your Bybit UID.

        :param member_id: The unique identifier of the member (your UID).
        :param coin: The name of the coin (e.g., "USDT").
        :param account_type: The type of account (e.g., "UNIFIED", "CLASSIC"). Defaults to "UNIFIED".
        :return: A dictionary containing the specific coin's balance details or None on failure.
        """
        if not isinstance(member_id, str) or not member_id:
            logger.error("Invalid 'member_id' provided for get_coin_balance.")
            return None
        if not isinstance(coin, str) or not coin:
            logger.error("Invalid 'coin' provided for get_coin_balance.")
            return None
        if not isinstance(account_type, str) or not account_type:
            logger.error("Invalid 'account_type' provided for get_coin_balance.")
            return None
        return self._make_request(
            "get_coin_balance",
            "Single Coin Balance",
            memberId=member_id,
            coin=coin,
            accountType=account_type,
        )

    def get_closed_pnl(
        self, category: str, symbol: str | None = None, **kwargs
    ) -> dict[str, Any] | None:
        """Queries closed profit and loss records for a given category and optional symbol.

        :param category: The product type (e.g., "linear", "inverse", "option").
        :param symbol: Optional. The trading symbol (e.g., "BTCUSDT").
        :param kwargs: Additional parameters like `limit`, `startTime`, `endTime`, `cursor`.
        :return: A dictionary containing a list of closed PnL records or None on failure.
        """
        if not isinstance(category, str) or not category:
            logger.error("Invalid 'category' provided for get_closed_pnl.")
            return None
        if symbol is not None and (not isinstance(symbol, str) or not symbol):
            logger.error("Invalid 'symbol' provided for get_closed_pnl.")
            return None

        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        params.update(kwargs)
        return self._make_request("get_closed_pnl", "Closed PnL Records", **params)

    def get_executions(
        self, category: str, symbol: str | None = None, **kwargs
    ) -> dict[str, Any] | None:
        """Retrieves execution history (detailed trade analysis) for a given category and optional symbol.

        :param category: The product type (e.g., "linear", "inverse", "option").
        :param symbol: Optional. The trading symbol (e.g., "BTCUSDT").
        :param kwargs: Additional parameters like `orderId`, `startTime`, `endTime`, `limit`, `cursor`.
        :return: A dictionary containing a list of execution records or None on failure.
        """
        if not isinstance(category, str) or not category:
            logger.error("Invalid 'category' provided for get_executions.")
            return None
        if symbol is not None and (not isinstance(symbol, str) or not symbol):
            logger.error("Invalid 'symbol' provided for get_executions.")
            return None

        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        params.update(kwargs)
        return self._make_request("get_executions", "Execution History", **params)

    def get_transaction_log(
        self, account_type: str = "UNIFIED", **kwargs
    ) -> dict[str, Any] | None:
        """Queries transaction logs for Unified accounts.

        :param account_type: The type of account (e.g., "UNIFIED"). Defaults to "UNIFIED".
        :param kwargs: Additional parameters like `category`, `currency`, `type`, `startTime`, `endTime`, `limit`.
        :return: A dictionary containing a list of transaction logs or None on failure.
        """
        if not isinstance(account_type, str) or not account_type:
            logger.error("Invalid 'account_type' provided for get_transaction_log.")
            return None

        params = {"accountType": account_type}
        params.update(kwargs)
        return self._make_request("get_transaction_log", "Transaction Log", **params)

    def get_borrow_history(
        self, currency: str | None = None, **kwargs
    ) -> dict[str, Any] | None:
        """Retrieves interest and borrowing records.

        :param currency: Optional. The name of the currency (e.g., "USDT").
        :param kwargs: Additional parameters like `bizType`, `startTime`, `endTime`, `limit`.
        :return: A dictionary containing a list of borrow history records or None on failure.
        """
        if currency is not None and (not isinstance(currency, str) or not currency):
            logger.error("Invalid 'currency' provided for get_borrow_history.")
            return None

        params = {}
        if currency:
            params["currency"] = currency
        params.update(kwargs)
        return self._make_request("get_borrow_history", "Borrow History", **params)

    def get_fee_rates(
        self, category: str, symbol: str | None = None
    ) -> dict[str, Any] | None:
        """Retrieves trading fee rates for derivatives (Linear, Inverse, Option).

        :param category: The product type (e.g., "linear", "inverse", "option").
        :param symbol: Optional. The trading symbol (e.g., "BTCUSDT").
        :return: A dictionary containing a list of fee rate information or None on failure.
        """
        if not isinstance(category, str) or not category:
            logger.error("Invalid 'category' provided for get_fee_rates.")
            return None
        if symbol is not None and (not isinstance(symbol, str) or not symbol):
            logger.error("Invalid 'symbol' provided for get_fee_rates.")
            return None

        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        return self._make_request("get_fee_rates", "Fee Rates", **params)

    def get_account_info(self) -> dict[str, Any] | None:
        """Queries margin mode configuration and other account details.

        :return: A dictionary containing account information or None on failure.
        """
        return self._make_request("get_account_info", "Account Info")


# Example Usage
if __name__ == "__main__":
    # IMPORTANT: Replace with your actual API key and secret.
    # For security, consider using environment variables (e.g., os.getenv("BYBIT_API_KEY")).
    # Set USE_TESTNET to False for production (mainnet).
    API_KEY = "YOUR_API_KEY"
    API_SECRET = "YOUR_API_SECRET"
    USE_TESTNET = True

    if API_KEY == "YOUR_API_KEY" or API_SECRET == "YOUR_API_SECRET":
        logger.error(
            "Please replace YOUR_API_KEY and YOUR_API_SECRET with your actual credentials in bybit_account_helper.py example."
        )
        # In a real application, you might exit or raise a more specific error.
        # For demonstration, we'll proceed but expect API calls to fail.
        # exit()

    account_helper = BybitAccountHelper(API_KEY, API_SECRET, testnet=USE_TESTNET)

    print("\n--- Getting Wallet Balance (Unified Account) ---")
    wallet_balance = account_helper.get_wallet_balance(account_type="UNIFIED")
    if wallet_balance and wallet_balance.get("list"):
        for account in wallet_balance["list"]:
            print(
                f"Account Type: {account.get('accountType')}, Total Equity: {account.get('totalEquity')}"
            )
            for coin_info in account.get("coin", []):
                print(
                    f"  Coin: {coin_info.get('coin')}, Available: {coin_info.get('availableToWithdraw')}, Wallet Balance: {coin_info.get('walletBalance')}"
                )
    else:
        print("  Failed to retrieve wallet balance or no accounts found.")

    print("\n--- Getting Transferable Amount for USDT ---")
    transferable_usdt = account_helper.get_transferable_amount(coin_name="USDT")
    if transferable_usdt:
        print(f"  USDT Transferable: {transferable_usdt.get('transferAbleAmount')}")
    else:
        print("  Failed to retrieve transferable amount for USDT.")

    # Note: To use get_coins_balance and get_coin_balance, you generally need your Bybit UID.
    # Replace "YOUR_UID" with your actual Bybit User ID if you want to test these.
    # You can often find your UID in your Bybit account settings.
    # MY_BYBIT_UID = "YOUR_UID"
    # if MY_BYBIT_UID != "YOUR_UID":
    #     print(f"\n--- Getting All Coins Balance for UID {MY_BYBIT_UID} ---")
    #     all_coins_balance = account_helper.get_coins_balance(member_id=MY_BYBIT_UID, account_type="UNIFIED")
    #     if all_coins_balance and all_coins_balance.get('list'):
    #         for coin_data in all_coins_balance['list']:
    #             print(f"  Coin: {coin_data.get('coin')}, Available: {coin_data.get('availableToWithdraw')}")
    #     else:
    #         print("  Failed to retrieve all coins balance.")

    print("\n--- Getting Closed PnL (Linear category, last 2 records) ---")
    closed_pnl = account_helper.get_closed_pnl(category="linear", limit=2)
    if closed_pnl and closed_pnl.get("list"):
        for record in closed_pnl["list"]:
            print(
                f"  Symbol: {record.get('symbol')}, PnL: {record.get('closedPnl')}, Side: {record.get('side')}, Created: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(record.get('createdTime')) / 1000))}"
            )
    else:
        print("  Failed to retrieve closed PnL records.")

    print("\n--- Getting Executions (Linear category, BTCUSDT, last 1 record) ---")
    executions = account_helper.get_executions(
        category="linear", symbol="BTCUSDT", limit=1
    )
    if executions and executions.get("list"):
        for exec_record in executions["list"]:
            print(
                f"  Symbol: {exec_record.get('symbol')}, Price: {exec_record.get('execPrice')}, Qty: {exec_record.get('execQty')}, Side: {exec_record.get('side')}"
            )
    else:
        print("  Failed to retrieve execution records.")

    print("\n--- Getting Fee Rates (Linear category, BTCUSDT) ---")
    fee_rates = account_helper.get_fee_rates(category="linear", symbol="BTCUSDT")
    if fee_rates and fee_rates.get("list"):
        rate_info = fee_rates["list"][0]
        print(
            f"  Symbol: {rate_info.get('symbol')}, Maker Fee: {rate_info.get('makerFeeRate')}, Taker Fee: {rate_info.get('takerFeeRate')}"
        )
    else:
        print("  Failed to retrieve fee rates.")

    print("\n--- Getting Account Info ---")
    account_info = account_helper.get_account_info()
    if account_info:
        print(
            f"  Unified Margin Account ID: {account_info.get('unifiedMarginAccount', {}).get('unifiedMarginAccountID')}"
        )
        print(f"  Margin Mode: {account_info.get('marginMode')}")
        print(f"  Spot Hedging Status: {account_info.get('spotHedgingStatus')}")
    else:
        print("  Failed to retrieve account information.")

    print("\n--- Getting Transaction Log (Unified Account, last 1 record) ---")
    transaction_log = account_helper.get_transaction_log(
        account_type="UNIFIED", limit=1
    )
    if transaction_log and transaction_log.get("list"):
        for log_entry in transaction_log["list"]:
            print(
                f"  Txn Type: {log_entry.get('type')}, Coin: {log_entry.get('coin')}, Amount: {log_entry.get('amount')}, Txn Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(log_entry.get('transactionTime')) / 1000))}"
            )
    else:
        print("  Failed to retrieve transaction log.")

    print("\n--- Getting Borrow History (USDT, last 1 record) ---")
    borrow_history = account_helper.get_borrow_history(currency="USDT", limit=1)
    if borrow_history and borrow_history.get("list"):
        for borrow_record in borrow_history["list"]:
            print(
                f"  Coin: {borrow_record.get('currency')}, Borrow Amount: {borrow_record.get('borrowAmount')}, Interest: {borrow_record.get('interest')}"
            )
    else:
        print("  Failed to retrieve borrow history.")
