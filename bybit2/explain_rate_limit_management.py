from colorama import Fore, Style, init

init(autoreset=True)


def explain_rate_limit_management():
    print(
        Fore.MAGENTA
        + "\n# Mastering the Flow: Effective Rate Limit Management for Bybit v5 API...\n"
        + Style.RESET_ALL
    )

    print(Fore.CYAN + "## The Nature of Rate Limits: Why They Exist" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "  API rate limits are put in place by exchanges like Bybit to protect their servers from being"
        "  overwhelmed by too many requests. Exceeding these limits can lead to your IP being temporarily"
        "  blocked or your requests being rejected." + Style.RESET_ALL
    )

    print(
        Fore.CYAN
        + "\n## Bybit v5 Rate Limit Headers: Your Guiding Stars"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  Bybit includes rate limit information in the response headers of each API call. These are crucial for dynamic management:"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - `X-Bapi-Limit-Status`: Current rate limit status (e.g., `OK`, `RATE_LIMITED`)."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - `X-Bapi-Limit-Retries`: Number of retries remaining for the current rate limit window."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - `X-Bapi-Limit-Reset-Timestamp`: Timestamp (in milliseconds) when the rate limit will reset."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - `X-Bapi-Limit`: The total limit for the current window."
        + Style.RESET_ALL
    )

    print(
        Fore.CYAN
        + "\n## Strategies for Effective Rate Limit Management:"
        + Style.RESET_ALL
    )
    print(Fore.YELLOW + "  1. **Understand Bybit's Limits:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - Refer to the official Bybit API documentation for the specific rate limits per endpoint and category."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "     - Limits vary for public vs. private endpoints, and different categories (spot, linear, inverse)."
        + Style.RESET_ALL
    )

    print(Fore.YELLOW + "  2. **Implement Delays (`time.sleep`):" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - The simplest form of rate limiting. Introduce a small delay between consecutive API calls."
        + Style.RESET_ALL
    )
    print(
        Fore.GREEN
        + "       `time.sleep(0.1)` # Sleep for 100 milliseconds between requests"
        + Style.RESET_ALL
    )

    print(Fore.YELLOW + "  3. **Exponential Backoff and Retries:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - When a `RATE_LIMITED` error (retCode 10006) is received, wait for an increasing amount of time before retrying."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "     - This prevents hammering the API and gives it time to recover."
        + Style.RESET_ALL
    )
    print(Fore.BLUE + "  Example Pseudo-code:" + Style.RESET_ALL)
    print(Fore.WHITE + "  ```python" + Style.RESET_ALL)
    print(Fore.WHITE + "  max_retries = 5" + Style.RESET_ALL)
    print(Fore.WHITE + "  for i in range(max_retries):" + Style.RESET_ALL)
    print(Fore.WHITE + "      try:" + Style.RESET_ALL)
    print(
        Fore.WHITE + "          response = session.some_api_call(...)" + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "          if response and response['retCode'] == 10006: # Rate limit error"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "              sleep_time = 2 ** i # Exponential backoff"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + '              print(f"Rate limited. Retrying in {sleep_time} seconds...")'
        + Style.RESET_ALL
    )
    print(Fore.WHITE + "              time.sleep(sleep_time)" + Style.RESET_ALL)
    print(Fore.WHITE + "              continue" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "          elif response and response['retCode'] == 0:"
        + Style.RESET_ALL
    )
    print(Fore.WHITE + "              # Success" + Style.RESET_ALL)
    print(Fore.WHITE + "              break" + Style.RESET_ALL)
    print(Fore.WHITE + "          else:" + Style.RESET_ALL)
    print(Fore.WHITE + "              # Handle other errors" + Style.RESET_ALL)
    print(Fore.WHITE + "              break" + Style.RESET_ALL)
    print(Fore.WHITE + "      except Exception as e:" + Style.RESET_ALL)
    print(Fore.WHITE + '          print(f"An error occurred: {e}")' + Style.RESET_ALL)
    print(Fore.WHITE + "          time.sleep(2 ** i)" + Style.RESET_ALL)
    print(Fore.WHITE + "  ```" + Style.RESET_ALL)

    print(
        Fore.YELLOW
        + "  4. **Utilize Response Headers for Dynamic Backoff:**"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "     - The most sophisticated approach. Parse `X-Bapi-Limit-Reset-Timestamp` to know exactly how long to wait."
        + Style.RESET_ALL
    )
    print(Fore.BLUE + "  Example Pseudo-code:" + Style.RESET_ALL)
    print(Fore.WHITE + "  ```python" + Style.RESET_ALL)
    print(Fore.WHITE + "  import datetime" + Style.RESET_ALL)
    print(Fore.WHITE + "  # ... (API call) ..." + Style.RESET_ALL)
    print(
        Fore.WHITE + "  if response and response['retCode'] == 10006:" + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "      reset_timestamp_ms = int(response['retMsg'].split('reset_timestamp:')[1].split(',')[0].strip())"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE + "      current_time_ms = int(time.time() * 1000)" + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "      wait_time_seconds = (reset_timestamp_ms - current_time_ms) / 1000 + 1 # Add 1 second buffer"
        + Style.RESET_ALL
    )
    print(Fore.WHITE + "      if wait_time_seconds > 0:" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + '          print(f"Rate limited. Waiting until {datetime.datetime.fromtimestamp(reset_timestamp_ms / 1000)} ({wait_time_seconds:.2f}s)")'
        + Style.RESET_ALL
    )
    print(Fore.WHITE + "          time.sleep(wait_time_seconds)" + Style.RESET_ALL)
    print(Fore.WHITE + "  ```" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "  (Note: The exact parsing of `retMsg` for `reset_timestamp` might vary slightly; always inspect the actual error message.)"
        + Style.RESET_ALL
    )

    print(Fore.YELLOW + "  5. **Batch Requests:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - If an endpoint allows fetching multiple items at once (e.g., multiple symbols' prices), use batching to reduce the number of API calls."
        + Style.RESET_ALL
    )

    print(Fore.YELLOW + "  6. **Caching:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - For data that doesn't change frequently (e.g., instrument info), cache the responses locally to avoid unnecessary API calls."
        + Style.RESET_ALL
    )

    print(Fore.YELLOW + "  7. **Asynchronous Programming (Advanced):" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - For high-throughput applications, consider `asyncio` in Python to manage multiple concurrent requests efficiently without blocking."
        + Style.RESET_ALL
    )

    print(
        Fore.MAGENTA
        + "\n# By mastering these techniques, your scripts will navigate the API with grace and avoid the wrath of rate limits!\n"
        + Style.RESET_ALL
    )


if __name__ == "__main__":
    explain_rate_limit_management()
