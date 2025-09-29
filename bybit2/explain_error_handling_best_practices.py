from colorama import Fore, Style, init

init(autoreset=True)


def explain_error_handling_best_practices():
    print(
        Fore.MAGENTA
        + "\n# Unveiling the Arcane Arts of Robust Error Handling in Bybit API Scripts...\n"
        + Style.RESET_ALL
    )

    print(Fore.CYAN + "## The First Principle: Anticipate and Catch!" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "  Always wrap your API calls in `try-except` blocks to gracefully handle exceptions."
        + Style.RESET_ALL
    )
    print(Fore.YELLOW + "  ### General Structure:" + Style.RESET_ALL)
    print(Fore.BLUE + "  try:" + Style.RESET_ALL)
    print(Fore.BLUE + "      response = session.some_api_call(...)" + Style.RESET_ALL)
    print(Fore.BLUE + "      # Process successful response" + Style.RESET_ALL)
    print(Fore.BLUE + "  except Exception as e:" + Style.RESET_ALL)
    print(Fore.BLUE + '      print(f"An error occurred: {e}")' + Style.RESET_ALL)
    print(
        Fore.BLUE
        + "      # Implement retry, logging, or notification logic"
        + Style.RESET_ALL
    )

    print(
        Fore.CYAN
        + "\n## Decoding Bybit API Error Codes (retCode and retMsg)"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  Bybit API responses include `retCode` (return code) and `retMsg` (return message)."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  `retCode` 0 usually indicates success. Non-zero `retCode` indicates an error."
        + Style.RESET_ALL
    )
    print(
        Fore.YELLOW
        + "  ### Common Error Codes and Handling Strategies:"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **`10001` (Parameter Error):** Invalid parameters. Check your request payload (symbol, quantity, price, etc.)."
        + Style.RESET_ALL
    )
    print(
        Fore.GREEN
        + "    `if response['retCode'] == 10001: print(\"Invalid parameter. Check your input.\")`"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **`10004` (Authentication Failed):** API key or secret is incorrect, or IP not whitelisted. Verify credentials and IP settings."
        + Style.RESET_ALL
    )
    print(
        Fore.GREEN
        + "    `if response['retCode'] == 10004: print(\"Authentication failed. Check API keys/IP.\")`"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **`10006` (Too Many Requests / Rate Limit):** You've hit the API rate limit. Implement delays or exponential backoff."
        + Style.RESET_ALL
    )
    print(
        Fore.GREEN
        + "    `if response['retCode'] == 10006: time.sleep(retry_after_seconds)`"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **`10007` (Signature Verification Failed):** Often due to incorrect API key/secret, or time synchronization issues. (See dedicated section for this)."
        + Style.RESET_ALL
    )
    print(
        Fore.GREEN
        + "    `if response['retCode'] == 10007: print(\"Signature error. Check time sync/keys.\")`"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **`10014` (Insufficient Balance):** Not enough funds for the order. Check your account balance before placing orders."
        + Style.RESET_ALL
    )
    print(
        Fore.GREEN
        + "    `if response['retCode'] == 10014: print(\"Insufficient balance.\")`"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **`10016` (Order Not Found):** When trying to cancel/amend a non-existent order. Check order ID."
        + Style.RESET_ALL
    )
    print(
        Fore.GREEN
        + "    `if response['retCode'] == 10016: print(\"Order not found.\")`"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **`10020` (Service Unavailable):** Temporary server issue. Implement retries."
        + Style.RESET_ALL
    )
    print(
        Fore.GREEN
        + "    `if response['retCode'] == 10020: print(\"Service unavailable. Retrying.\")`"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **`10021` (Order Price Exceeds Limit):** Price is too far from market price. Adjust price or use market order."
        + Style.RESET_ALL
    )
    print(
        Fore.GREEN
        + "    `if response['retCode'] == 10021: print(\"Price too far from market.\")`"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **`10022` (Order Quantity Exceeds Limit):** Quantity is too large/small. Check min/max order quantity for the symbol."
        + Style.RESET_ALL
    )
    print(
        Fore.GREEN
        + "    `if response['retCode'] == 10022: print(\"Quantity out of bounds.\")`"
        + Style.RESET_ALL
    )

    print(Fore.CYAN + "\n## Robust Error Handling Strategies:" + Style.RESET_ALL)
    print(Fore.YELLOW + "  1. **Specific Exception Handling:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - Catch specific exceptions (e.g., `requests.exceptions.ConnectionError` for network issues) before a general `Exception`."
        + Style.RESET_ALL
    )
    print(
        Fore.YELLOW
        + "  2. **Retry Mechanisms with Exponential Backoff:**"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "     - For transient errors (rate limits, service unavailable), don't immediately retry. Wait for increasing periods."
        + Style.RESET_ALL
    )
    print(Fore.WHITE + "     - Example: `time.sleep(2**retry_count)`" + Style.RESET_ALL)
    print(Fore.YELLOW + "  3. **Logging:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - Log all errors with timestamps, `retCode`, `retMsg`, and relevant context (e.g., API endpoint, parameters)."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "     - Use Python's `logging` module for structured logs."
        + Style.RESET_ALL
    )
    print(Fore.YELLOW + "  4. **Alerting/Notifications:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - For critical errors (e.g., authentication failure, repeated order failures), send a Termux notification or email."
        + Style.RESET_ALL
    )
    print(Fore.YELLOW + "  5. **Circuit Breaker Pattern:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - If an external service (Bybit API) is consistently failing, temporarily stop making requests to it to prevent cascading failures."
        + Style.RESET_ALL
    )
    print(Fore.YELLOW + "  6. **Input Validation:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - Validate all inputs to your functions *before* making API calls to catch common errors early."
        + Style.RESET_ALL
    )
    print(Fore.YELLOW + "  7. **Graceful Degradation:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - If a non-critical API call fails, allow your script to continue functioning in a degraded mode if possible."
        + Style.RESET_ALL
    )

    print(
        Fore.MAGENTA
        + "\n# With these wards, your scripts shall be more resilient against the digital storms!\n"
        + Style.RESET_ALL
    )


if __name__ == "__main__":
    explain_error_handling_best_practices()
