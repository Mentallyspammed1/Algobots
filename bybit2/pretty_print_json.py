import json

from colorama import Fore
from colorama import Style
from colorama import init

init(autoreset=True)


def pretty_print_json(data):
    print(
        Fore.MAGENTA
        + "\n# Unveiling the raw JSON response with mystical clarity...\n"
        + Style.RESET_ALL
    )
    try:
        # Use json.dumps for pretty printing
        pretty_json = json.dumps(data, indent=4, sort_keys=True)
        print(Fore.WHITE + pretty_json + Style.RESET_ALL)
        print(
            Fore.GREEN
            + "  # JSON response pretty-printed successfully!"
            + Style.RESET_ALL
        )
    except TypeError as e:
        print(
            Fore.RED
            + f"  # Error: The provided data is not valid JSON or a JSON-serializable Python object: {e}"
            + Style.RESET_ALL
        )
        print(
            Fore.YELLOW
            + "  # Please ensure you pass a dictionary or list that can be converted to JSON."
            + Style.RESET_ALL
        )
    except Exception as e:
        print(
            Fore.RED
            + f"  # An unexpected error occurred during pretty-printing: {e}"
            + Style.RESET_ALL
        )
    print(Fore.MAGENTA + "\n# The raw data has been illuminated!\n" + Style.RESET_ALL)


if __name__ == "__main__":
    # Example usage with a dummy Bybit API response structure
    dummy_response = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "lastPrice": "29500.50",
                    "volume24h": "12345.67",
                    "turnover24h": "364876543.21",
                },
                {
                    "symbol": "ETHUSDT",
                    "lastPrice": "1850.75",
                    "volume24h": "98765.43",
                    "turnover24h": "18273645.98",
                },
            ]
        },
        "time": 1678886400000,
    }

    print(
        Fore.YELLOW
        + "  # Demonstrating pretty-printing with a sample Bybit API response."
        + Style.RESET_ALL
    )
    pretty_print_json(dummy_response)

    print(
        Fore.YELLOW
        + "\n  # Demonstrating pretty-printing with a simple Python dictionary."
        + Style.RESET_ALL
    )
    simple_dict = {"name": "Pyrmethus", "age": "ancient", "powers": ["coding", "magic"]}
    pretty_print_json(simple_dict)

    print(
        Fore.YELLOW
        + "\n  # Demonstrating error handling with invalid data."
        + Style.RESET_ALL
    )
    invalid_data = "This is not JSON"
    pretty_print_json(invalid_data)
