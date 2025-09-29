# bybit_broker_helper.py
import logging
from typing import Any

from pybit.exceptions import BybitAPIError, BybitRequestError
from pybit.unified_trading import HTTP

# Configure logging for the module
logging.basicConfig(
    level=logging.INFO,  # Changed to INFO for less verbose default output, DEBUG for full details
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


class BybitBrokerHelper:
    """A helper class for managing Bybit broker-related functionalities,
    including retrieving broker information, earnings, and sub-account details
    for users participating in the Bybit Broker program.
    All functions require API key authentication.
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        """Initializes the BybitBrokerHelper with API credentials and environment.

        :param api_key: Your Bybit API key.
        :param api_secret: Your Bybit API secret.
        :param testnet: Set to True to connect to the Bybit testnet, False for mainnet.
        """
        if not api_key or not api_secret:
            logger.error("API Key and Secret are required for BybitBrokerHelper.")
            raise ValueError("API Key and Secret must be provided.")

        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.session = HTTP(
            testnet=self.testnet, api_key=self.api_key, api_secret=self.api_secret
        )
        logger.info(
            f"BybitBrokerHelper initialized for {'testnet' if self.testnet else 'mainnet'}."
        )

    def _make_request(
        self, method: str, endpoint_name: str, **kwargs
    ) -> dict[str, Any] | None:
        """Internal method to make an HTTP request to the Bybit API and handle responses.
        It centralizes error handling and logging for API calls.

        :param method: The name of the method to call on the `self.session` object.
        :param endpoint_name: A descriptive name for the API endpoint, used in logging.
        :param kwargs: Keyword arguments to pass directly to the `pybit` API method.
        :return: The 'result' dictionary from the API response if the call is successful (retCode == 0),
                 otherwise returns None after logging the error.
        """
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

    def get_broker_info(self) -> dict[str, Any] | None:
        """Retrieves general information about the broker.

        :return: A dictionary containing broker information or None on failure.
        """
        return self._make_request("get_broker_info", "Broker Info")

    def get_broker_earnings(
        self, biz_type: str | None = None, **kwargs
    ) -> dict[str, Any] | None:
        """Retrieves broker earnings records.

        :param biz_type: Optional. Business type (e.g., "SPOT", "LINEAR", "INVERSE", "OPTION").
                         If not provided, returns earnings for all business types.
        :param kwargs: Additional optional parameters (e.g., `startTime`, `endTime`, `limit`).
        :return: A dictionary containing a list of broker earnings records or None on failure.
        """
        if biz_type is not None and (not isinstance(biz_type, str) or not biz_type):
            logger.error("Invalid 'biz_type' provided for get_broker_earnings.")
            return None

        params = {}
        if biz_type:
            params["bizType"] = biz_type
        params.update(kwargs)
        return self._make_request("get_broker_earnings", "Broker Earnings", **params)

    def get_broker_account_info(
        self, sub_member_id: int | None = None
    ) -> dict[str, Any] | None:
        """Retrieves sub-account information for a broker.

        :param sub_member_id: Optional. The UID of the sub-account. If not provided,
                              returns information for all sub-accounts.
        :return: A dictionary containing a list of broker sub-account information or None on failure.
        """
        params = {}
        if sub_member_id is not None:
            if not isinstance(sub_member_id, int) or sub_member_id <= 0:
                logger.error(
                    "Invalid 'sub_member_id' provided for get_broker_account_info."
                )
                return None
            params["subMemberId"] = sub_member_id
        return self._make_request(
            "get_broker_account_info", "Broker Account Info", **params
        )


# Example Usage
if __name__ == "__main__":
    # IMPORTANT: Replace with your actual API key and secret.
    # These functions are typically for accounts enrolled in the Bybit Broker program.
    # For security, consider using environment variables.
    API_KEY = "YOUR_BROKER_API_KEY"
    API_SECRET = "YOUR_BROKER_API_SECRET"
    USE_TESTNET = True

    if API_KEY == "YOUR_BROKER_API_KEY" or API_SECRET == "YOUR_BROKER_API_SECRET":
        logger.error(
            "Please replace YOUR_BROKER_API_KEY and YOUR_BROKER_API_SECRET with your actual credentials in bybit_broker_helper.py example."
        )
        logger.error(
            "Note: Broker functions are for accounts enrolled in the Bybit Broker program."
        )
        # For demonstration, we'll proceed but expect API calls to fail if not a broker account.
        # exit()

    broker_helper = BybitBrokerHelper(API_KEY, API_SECRET, testnet=USE_TESTNET)

    print("\n--- Getting Broker Info ---")
    broker_info = broker_helper.get_broker_info()
    if broker_info:
        print(
            f"  Broker ID: {broker_info.get('brokerId')}, Name: {broker_info.get('brokerName')}"
        )
        print(f"  Deposit Bonus Total: {broker_info.get('depositBonusTotal')}")
    else:
        print("  Failed to retrieve broker info (Are you a broker?).")

    print("\n--- Getting Broker Earnings (SPOT category) ---")
    broker_earnings_spot = broker_helper.get_broker_earnings(biz_type="SPOT", limit=2)
    if broker_earnings_spot and broker_earnings_spot.get("list"):
        print("  SPOT Earnings Records:")
        for record in broker_earnings_spot["list"]:
            print(
                f"    Date: {record.get('bizDate')}, Income: {record.get('totalIncome')}, Biz Type: {record.get('bizType')}"
            )
    else:
        print("  Failed to retrieve SPOT broker earnings or no records found.")

    print("\n--- Getting Broker Earnings (LINEAR category) ---")
    broker_earnings_linear = broker_helper.get_broker_earnings(
        biz_type="LINEAR", limit=2
    )
    if broker_earnings_linear and broker_earnings_linear.get("list"):
        print("  LINEAR Earnings Records:")
        for record in broker_earnings_linear["list"]:
            print(
                f"    Date: {record.get('bizDate')}, Income: {record.get('totalIncome')}, Biz Type: {record.get('bizType')}"
            )
    else:
        print("  Failed to retrieve LINEAR broker earnings or no records found.")

    print("\n--- Getting Broker Account Info (All Sub-Members) ---")
    broker_account_info = broker_helper.get_broker_account_info()
    if broker_account_info and broker_account_info.get("list"):
        print("  Broker Sub-Account Info:")
        for account in broker_account_info["list"]:
            print(
                f"    SubMemberId: {account.get('subMemberId')}, Username: {account.get('username')}, Status: {account.get('status')}"
            )
    else:
        print("  Failed to retrieve broker sub-account info or no records found.")
