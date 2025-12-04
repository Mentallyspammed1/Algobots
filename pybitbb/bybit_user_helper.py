# bybit_user_helper.py
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


class BybitUserHelper:
    """A helper class for managing Bybit user-related functionalities,
    including API key management, sub-account operations, and affiliate information.
    All functions require API key authentication.
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        """Initializes the BybitUserHelper with API credentials and environment.

        :param api_key: Your Bybit API key.
        :param api_secret: Your Bybit API secret.
        :param testnet: Set to True to connect to the Bybit testnet, False for mainnet.
        """
        if not api_key or not api_secret:
            logger.error("API Key and Secret are required for BybitUserHelper.")
            raise ValueError("API Key and Secret must be provided.")

        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.session = HTTP(
            testnet=self.testnet, api_key=self.api_key, api_secret=self.api_secret,
        )
        logger.info(
            f"BybitUserHelper initialized for {'testnet' if self.testnet else 'mainnet'}.",
        )

    def _make_request(
        self, method: str, endpoint_name: str, **kwargs,
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
                    f"[{endpoint_name}] Successfully called. Response: {response.get('result')}",
                )
                return response.get("result")
            ret_code = response.get("retCode", "N/A")
            error_msg = response.get("retMsg", "Unknown error")
            logger.error(
                f"[{endpoint_name}] API call failed. Code: {ret_code}, Message: {error_msg}. "
                f"Args: {kwargs}. Full Response: {response}",
            )
            return None
        except (BybitRequestError, BybitAPIError) as e:
            logger.exception(
                f"[{endpoint_name}] Pybit specific error during API call. "
                f"Args: {kwargs}. Error: {e}",
            )
            return None
        except Exception as e:
            logger.exception(
                f"[{endpoint_name}] Unexpected exception during API call. "
                f"Args: {kwargs}. Error: {e}",
            )
            return None

    # --- API Key Management ---
    def get_api_key_info(self) -> dict[str, Any] | None:
        """Retrieves information about the current API key.

        :return: A dictionary containing API key details or None on failure.
        """
        return self._make_request("get_api_key_info", "API Key Info")

    def modify_master_api_key(
        self,
        read_only: int,
        ips: list[str] | None = None,
        permissions: dict[str, list[str]] | None = None,
    ) -> dict[str, Any] | None:
        """Modifies permissions or IP restrictions for the master API key.
        Use with extreme caution, as this modifies the key currently in use.

        :param read_only: 0 for read/write, 1 for read-only.
        :param ips: Optional. List of IP addresses to bind to (e.g., ["192.168.1.1", "1.1.1.1"]).
        :param permissions: Optional. Dictionary of permissions (e.g., {"ContractTrade": ["Order", "Position"]}).
        :return: A dictionary containing the modification response or None on failure.
        """
        if not isinstance(read_only, int) or read_only not in [0, 1]:
            logger.error("Invalid 'read_only' parameter. Must be 0 or 1.")
            return None
        if ips is not None and (
            not isinstance(ips, list) or not all(isinstance(ip, str) for ip in ips)
        ):
            logger.error("Invalid 'ips' parameter. Must be a list of strings.")
            return None
        if permissions is not None and not isinstance(permissions, dict):
            logger.error("Invalid 'permissions' parameter. Must be a dictionary.")
            return None

        params = {"readOnly": read_only}
        if ips:
            params["ips"] = ips
        if permissions:
            params["permissions"] = permissions

        logger.warning(
            "Attempting to modify the master API key. This is a sensitive operation.",
        )
        return self._make_request(
            "modify_master_api_key", "Modify Master API Key", **params,
        )

    def delete_master_api_key(self) -> dict[str, Any] | None:
        """Deletes the master API key currently in use.
        This will invalidate the current helper instance. Use with extreme caution.

        :return: A dictionary containing the deletion response or None on failure.
        """
        logger.critical(
            "Attempting to DELETE the master API key. This will invalidate the current API credentials.",
        )
        return self._make_request("delete_master_api_key", "Delete Master API Key")

    # --- Sub-Account Management ---
    def create_sub_uid(
        self, username: str, member_type: int = 1,
    ) -> dict[str, Any] | None:
        """Creates a new sub-UID (sub-account).

        :param username: The username for the new sub-account.
        :param member_type: Type of sub-account (1 for normal, 6 for Custodian). Defaults to 1.
        :return: A dictionary containing the new sub-UID and username or None on failure.
        """
        if not isinstance(username, str) or not username:
            logger.error("Invalid 'username' provided for create_sub_uid.")
            return None
        if not isinstance(member_type, int) or member_type not in [1, 6]:
            logger.error(
                "Invalid 'member_type' provided for create_sub_uid. Must be 1 or 6.",
            )
            return None

        params = {"username": username, "memberType": member_type}
        return self._make_request("create_sub_uid", "Create Sub-UID", **params)

    def get_sub_uid_list(self) -> dict[str, Any] | None:
        """Retrieves a list of all sub-UIDs (sub-accounts) under the master account.

        :return: A dictionary containing a list of sub-UIDs or None on failure.
        """
        return self._make_request("get_sub_uid_list", "Get Sub-UID List")

    def freeze_sub_uid(self, sub_uid: int, frozen: int) -> dict[str, Any] | None:
        """Freezes or unfreezes a sub-UID.

        :param sub_uid: The UID of the sub-account to freeze/unfreeze.
        :param frozen: 1 to freeze, 0 to unfreeze.
        :return: A dictionary containing the operation response or None on failure.
        """
        if not isinstance(sub_uid, int) or sub_uid <= 0:
            logger.error(
                "Invalid 'sub_uid' provided for freeze_sub_uid. Must be a positive integer.",
            )
            return None
        if not isinstance(frozen, int) or frozen not in [0, 1]:
            logger.error(
                "Invalid 'frozen' parameter. Must be 0 (unfreeze) or 1 (freeze).",
            )
            return None

        params = {"subuid": sub_uid, "frozen": frozen}
        return self._make_request("freeze_sub_uid", "Freeze Sub-UID", **params)

    def create_sub_api_key(
        self,
        sub_uid: int,
        read_only: int,
        ips: list[str] | None = None,
        permissions: dict[str, list[str]] | None = None,
        note: str | None = None,
    ) -> dict[str, Any] | None:
        """Creates an API key for a specific sub-UID.

        :param sub_uid: The UID of the sub-account.
        :param read_only: 0 for read/write, 1 for read-only.
        :param ips: Optional. List of IP addresses to bind to.
        :param permissions: Optional. Dictionary of permissions.
        :param note: Optional. Remarks for the API key.
        :return: A dictionary containing the new sub-account API key details or None on failure.
        """
        if not isinstance(sub_uid, int) or sub_uid <= 0:
            logger.error("Invalid 'sub_uid' provided for create_sub_api_key.")
            return None
        if not isinstance(read_only, int) or read_only not in [0, 1]:
            logger.error("Invalid 'read_only' parameter. Must be 0 or 1.")
            return None
        if ips is not None and (
            not isinstance(ips, list) or not all(isinstance(ip, str) for ip in ips)
        ):
            logger.error("Invalid 'ips' parameter. Must be a list of strings.")
            return None
        if permissions is not None and not isinstance(permissions, dict):
            logger.error("Invalid 'permissions' parameter. Must be a dictionary.")
            return None
        if note is not None and not isinstance(note, str):
            logger.error("Invalid 'note' parameter. Must be a string.")
            return None

        params = {"subuid": sub_uid, "readOnly": read_only}
        if ips:
            params["ips"] = ips
        if permissions:
            params["permissions"] = permissions
        if note:
            params["note"] = note
        return self._make_request(
            "create_sub_api_key", "Create Sub-Account API Key", **params,
        )

    def get_all_sub_api_keys(
        self, sub_member_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Retrieves all API keys for a specific sub-UID or all sub-UIDs if `sub_member_id` is None.

        :param sub_member_id: Optional. The UID of the sub-account.
        :return: A dictionary containing a list of sub-account API keys or None on failure.
        """
        params = {}
        if sub_member_id is not None:
            if not isinstance(sub_member_id, int) or sub_member_id <= 0:
                logger.error(
                    "Invalid 'sub_member_id' provided for get_all_sub_api_keys.",
                )
                return None
            params["subMemberId"] = sub_member_id
        return self._make_request(
            "get_all_sub_api_keys", "Get All Sub-Account API Keys", **params,
        )

    def delete_sub_api_key(self, api_key_to_delete: str) -> dict[str, Any] | None:
        """Deletes a specific sub-account API key.

        :param api_key_to_delete: The API key string of the sub-account to delete.
        :return: A dictionary containing the deletion response or None on failure.
        """
        if not isinstance(api_key_to_delete, str) or not api_key_to_delete:
            logger.error("Invalid 'api_key_to_delete' provided for delete_sub_api_key.")
            return None

        params = {"apikey": api_key_to_delete}
        logger.warning(
            f"Attempting to DELETE sub-account API key: {api_key_to_delete}. This is irreversible.",
        )
        return self._make_request(
            "delete_sub_api_key", "Delete Sub-Account API Key", **params,
        )

    # --- Affiliate Information ---
    def get_affiliate_user_info(self, uid: int | None = None) -> dict[str, Any] | None:
        """Retrieves affiliate user information.

        :param uid: Optional. User ID to query. If not provided, queries for the current API key's user.
        :return: A dictionary containing affiliate user information or None on failure.
        """
        params = {}
        if uid is not None:
            if not isinstance(uid, int) or uid <= 0:
                logger.error("Invalid 'uid' provided for get_affiliate_user_info.")
                return None
            params["uid"] = uid
        return self._make_request(
            "get_affiliate_user_info", "Get Affiliate User Info", **params,
        )


# Example Usage
if __name__ == "__main__":
    # IMPORTANT: Replace with your actual MASTER API key and secret.
    # Sub-account management requires master account API credentials.
    # For security, consider using environment variables.
    API_KEY = "YOUR_MASTER_API_KEY"
    API_SECRET = "YOUR_MASTER_API_SECRET"
    USE_TESTNET = True

    if API_KEY == "YOUR_MASTER_API_KEY" or API_SECRET == "YOUR_MASTER_API_SECRET":
        logger.error(
            "Please replace YOUR_MASTER_API_KEY and YOUR_MASTER_API_SECRET with your actual credentials in bybit_user_helper.py example.",
        )
        # For demonstration, we'll proceed but expect API calls to fail.
        # exit()

    user_helper = BybitUserHelper(API_KEY, API_SECRET, testnet=USE_TESTNET)

    # --- API Key Management ---
    print("\n--- Getting Master API Key Info ---")
    api_key_info = user_helper.get_api_key_info()
    if api_key_info and api_key_info.get("list"):
        key_details = api_key_info["list"][0]
        print(
            f"  API Key: {key_details.get('apiKey')}, Read-Only: {key_details.get('readOnly')}, Permissions: {key_details.get('permissions')}, IPs: {key_details.get('ips')}",
        )
    else:
        print("  Failed to retrieve API key info.")

    # --- Sub-Account Management ---
    # Note: Creating/deleting sub-accounts and their API keys should be done carefully.
    # This example will demonstrate listing and freezing.

    print("\n--- Getting Sub-UID List ---")
    sub_uid_list = user_helper.get_sub_uid_list()
    target_sub_uid = None
    if sub_uid_list and sub_uid_list.get("list"):
        print("  Existing Sub-UIDs:")
        for sub_account in sub_uid_list["list"]:
            print(
                f"    Username: {sub_account.get('username')}, UID: {sub_account.get('uid')}, Status: {'Frozen' if sub_account.get('frozen') == 1 else 'Active'}",
            )
            if not target_sub_uid:  # Pick the first one for demonstration
                target_sub_uid = sub_account.get("uid")
    else:
        print(
            "  No sub-UIDs found or failed to retrieve list. (You might need to create one first.)",
        )
        # Example of creating a sub-UID if none exist (uncomment with caution)
        # new_sub_username = f"testsub_{int(time.time())}"
        # print(f"\n--- Creating new sub-UID: {new_sub_username} ---")
        # new_sub_response = user_helper.create_sub_uid(username=new_sub_username)
        # if new_sub_response:
        #     target_sub_uid = new_sub_response.get('uid')
        #     print(f"  New sub-UID created: {new_sub_response}")
        # else:
        #     print("  Failed to create sub-UID.")

    if target_sub_uid:
        print(f"\n--- Freezing Sub-UID: {target_sub_uid} ---")
        freeze_response = user_helper.freeze_sub_uid(sub_uid=target_sub_uid, frozen=1)
        if freeze_response:
            print(f"  Freeze response: {freeze_response}")
        else:
            print("  Failed to freeze sub-UID.")

        print(f"\n--- Unfreezing Sub-UID: {target_sub_uid} ---")
        unfreeze_response = user_helper.freeze_sub_uid(sub_uid=target_sub_uid, frozen=0)
        if unfreeze_response:
            print(f"  Unfreeze response: {unfreeze_response}")
        else:
            print("  Failed to unfreeze sub-UID.")

        print(f"\n--- Getting API Keys for Sub-UID: {target_sub_uid} ---")
        sub_api_keys = user_helper.get_all_sub_api_keys(sub_member_id=target_sub_uid)
        if sub_api_keys and sub_api_keys.get("list"):
            print(f"  API Keys for Sub-UID {target_sub_uid}:")
            for key in sub_api_keys["list"]:
                print(
                    f"    API Key: {key.get('apiKey')}, Read-Only: {key.get('readOnly')}, Permissions: {key.get('permissions')}",
                )
        else:
            print(
                f"  No API keys found for Sub-UID {target_sub_uid} or failed to retrieve.",
            )
            # Example of creating a sub-account API key (uncomment with caution)
            # new_sub_api_key_response = user_helper.create_sub_api_key(
            #     sub_uid=target_sub_uid,
            #     read_only=0,
            #     note=f"TestKey_{int(time.time())}",
            #     permissions={"ContractTrade": ["Order", "Position"]}
            # )
            # if new_sub_api_key_response:
            #     print(f"  New Sub-Account API Key created: {new_sub_api_key_response}")
            #     # Store this API key to delete it later if needed
            # else:
            #     print("  Failed to create sub-account API key.")

    # --- Affiliate Information ---
    print("\n--- Getting Affiliate User Info (for current API key's user) ---")
    affiliate_info = user_helper.get_affiliate_user_info()
    if affiliate_info:
        print(f"  Affiliate Info: {affiliate_info}")
    else:
        print("  Failed to retrieve affiliate user info.")
