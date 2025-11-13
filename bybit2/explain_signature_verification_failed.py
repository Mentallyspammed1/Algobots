from colorama import Fore
from colorama import Style
from colorama import init

init(autoreset=True)


def explain_signature_verification_failed():
    print(
        Fore.MAGENTA
        + "\n# Deciphering the 'Signature Verification Failed' Enigma...\n"
        + Style.RESET_ALL
    )

    print(
        Fore.CYAN
        + "## The Nature of the Beast: Signature Verification"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  Bybit, like most secure exchanges, requires every private API request to be signed."
        "  This signature is a cryptographic hash generated using your API key, API secret, and the request parameters."
        "  It ensures that the request truly originates from you and hasn't been tampered with."
        + Style.RESET_ALL
    )

    print(
        Fore.CYAN
        + "\n## Common Reasons for 'Signature Verification Failed' (retCode: 10007):"
        + Style.RESET_ALL
    )
    print(Fore.YELLOW + "  1. **Incorrect API Key or Secret:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - This is the most frequent culprit. Double-check that your `BYBIT_API_KEY` and `BYBIT_API_SECRET`"
        "       in your `.env` file or environment variables are exact matches to those generated on Bybit."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "     - Ensure there are no leading/trailing spaces or hidden characters."
        + Style.RESET_ALL
    )
    print(
        Fore.YELLOW
        + "  2. **Time Synchronization Issues (NTP Sync):**"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "     - The Bybit API has a strict timestamp tolerance (usually within a few seconds). If your system's clock"
        "       is out of sync with Bybit's servers, the signature will be invalid."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "     - **Termux Solution:** Use `ntpdate` or `termux-setup-storage` (which often helps with time sync)."
        "       `pkg install ntpdate` then `sudo ntpdate pool.ntp.org` (requires root, which is not typical for Termux)."
        "       A simpler approach is to ensure your Android device's time is set to automatic network time."
        + Style.RESET_ALL
    )
    print(
        Fore.YELLOW
        + "  3. **Incorrect Request Parameters or Order:**"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "     - The signature is generated based on the exact parameters and their order. If you're manually constructing"
        "       requests or using a library incorrectly, the parameters sent might not match what's being signed."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "     - **Pybit Library:** The `pybit` library handles this automatically, which is why it's recommended. If you're"
        "       seeing this error with `pybit`, it's less likely to be this reason unless you're passing malformed data."
        + Style.RESET_ALL
    )
    print(Fore.YELLOW + "  4. **IP Whitelisting:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - If you have IP whitelisting enabled for your API key on Bybit, and your Termux's external IP address"
        "       is not on that whitelist, your requests will be rejected with a signature error."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "     - **Solution:** Disable IP whitelisting (less secure) or add your Termux's public IP to the whitelist."
        + Style.RESET_ALL
    )
    print(Fore.YELLOW + "  5. **API Key Permissions:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - Ensure your API key has the necessary permissions for the endpoint you are trying to access (e.g., Read, Trade)."
        "       A lack of permission might sometimes manifest as a signature error."
        + Style.RESET_ALL
    )

    print(Fore.CYAN + "\n## Debugging Strategies:" + Style.RESET_ALL)
    print(Fore.YELLOW + "  1. **Verify API Keys:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - Print the API key and secret (temporarily, for debugging only!) that your script is using to ensure they are loaded correctly."
        + Style.RESET_ALL
    )
    print(Fore.GREEN + '       `print(f"API Key: {api_key}")`' + Style.RESET_ALL)
    print(Fore.YELLOW + "  2. **Check System Time:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - Compare your Termux system time with Bybit's server time. Use the `get_bybit_server_time.py` script I provided."
        + Style.RESET_ALL
    )
    print(Fore.GREEN + "       `python get_bybit_server_time.py`" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - If there's a significant difference, adjust your Android device's time settings to automatic."
        + Style.RESET_ALL
    )
    print(Fore.YELLOW + "  3. **Simplify the Request:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - Try making the simplest possible authenticated request (e.g., fetching account balance) to isolate the issue."
        + Style.RESET_ALL
    )
    print(Fore.YELLOW + "  4. **Review Bybit API Documentation:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - Double-check the specific endpoint's requirements in the official Bybit API documentation for any subtle parameter nuances."
        + Style.RESET_ALL
    )
    print(Fore.YELLOW + "  5. **Test on Testnet:**" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "     - Always test your API keys and scripts on the Bybit Testnet first. This prevents issues on your live account."
        + Style.RESET_ALL
    )

    print(
        Fore.MAGENTA
        + "\n# May your signatures always be valid, and your API calls successful!\n"
        + Style.RESET_ALL
    )


if __name__ == "__main__":
    explain_signature_verification_failed()
