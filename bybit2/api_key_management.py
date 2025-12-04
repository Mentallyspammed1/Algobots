from colorama import Fore, Style, init

init(autoreset=True)


def explain_api_key_management():
    print(
        Fore.MAGENTA
        + "\n# Unveiling the Arcane Secrets of API Key Management in Termux...\n"
        + Style.RESET_ALL,
    )

    print(
        Fore.CYAN + "## The First Principle: Never Hardcode Secrets!" + Style.RESET_ALL,
    )
    print(
        Fore.WHITE
        + "  Hardcoding API keys directly into your scripts is akin to leaving your vault wide open."
        "  It's a grave security risk, especially if your code is ever shared or committed to version control."
        "  We shall employ more secure incantations." + Style.RESET_ALL,
    )

    print(
        Fore.CYAN
        + "\n## Method 1: Environment Variables (The Elemental Way)"
        + Style.RESET_ALL,
    )
    print(
        Fore.WHITE
        + "  This method involves setting your API keys as system-wide or session-specific environment variables."
        "  They are not stored directly in your script, making them safer."
        + Style.RESET_ALL,
    )
    print(
        Fore.YELLOW
        + "  ### How to Set in Termux (Temporary for current session):"
        + Style.RESET_ALL,
    )
    print(Fore.GREEN + '  export BYBIT_API_KEY="YOUR_API_KEY"' + Style.RESET_ALL)
    print(Fore.GREEN + '  export BYBIT_API_SECRET="YOUR_API_SECRET"' + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "  (Replace YOUR_API_KEY and YOUR_API_SECRET with your actual keys.)"
        + Style.RESET_ALL,
    )
    print(
        Fore.YELLOW
        + "  ### How to Set in Termux (Persistent - add to ~/.bashrc or ~/.zshrc):"
        + Style.RESET_ALL,
    )
    print(
        Fore.GREEN
        + "  echo 'export BYBIT_API_KEY=\"YOUR_API_KEY\"' >> ~/.bashrc"
        + Style.RESET_ALL,
    )
    print(
        Fore.GREEN
        + "  echo 'export BYBIT_API_SECRET=\"YOUR_API_SECRET\"' >> ~/.bashrc"
        + Style.RESET_ALL,
    )
    print(
        Fore.WHITE
        + "  Then, source your bashrc: "
        + Fore.GREEN
        + "source ~/.bashrc"
        + Style.RESET_ALL,
    )
    print(Fore.YELLOW + "  ### How to Access in Python:" + Style.RESET_ALL)
    print(Fore.BLUE + "  import os" + Style.RESET_ALL)
    print(Fore.BLUE + "  api_key = os.getenv('BYBIT_API_KEY')" + Style.RESET_ALL)
    print(Fore.BLUE + "  api_secret = os.getenv('BYBIT_API_SECRET')" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "  (If a variable is not set, os.getenv will return None.)"
        + Style.RESET_ALL,
    )

    print(
        Fore.CYAN
        + "\n## Method 2: .env File (The Encapsulated Scroll)"
        + Style.RESET_ALL,
    )
    print(
        Fore.WHITE
        + "  This method is often preferred for development environments. You create a file named `.env`"
        "  in your project's root directory and store your key-value pairs there. You then use a library"
        "  like `python-dotenv` to load these variables into your script's environment."
        + Style.RESET_ALL,
    )
    print(
        Fore.YELLOW
        + "  ### Step 1: Create a `.env` file in your project directory:"
        + Style.RESET_ALL,
    )
    print(Fore.GREEN + "  # .env content" + Style.RESET_ALL)
    print(Fore.GREEN + "  BYBIT_API_KEY=YOUR_API_KEY" + Fore.GREEN + Style.RESET_ALL)
    print(
        Fore.GREEN + "  BYBIT_API_SECRET=YOUR_API_SECRET" + Fore.GREEN + Style.RESET_ALL,
    )
    print(
        Fore.WHITE
        + "  (Remember to add `.env` to your `.gitignore` file if using Git!)"
        + Style.RESET_ALL,
    )
    print(
        Fore.YELLOW
        + "  ### Step 2: Install `python-dotenv` (if you haven't already):"
        + Style.RESET_ALL,
    )
    print(Fore.GREEN + "  pip install python-dotenv" + Style.RESET_ALL)
    print(Fore.YELLOW + "  ### Step 3: Access in Python:" + Style.RESET_ALL)
    print(Fore.BLUE + "  from dotenv import load_dotenv" + Style.RESET_ALL)
    print(Fore.BLUE + "  import os" + Style.RESET_ALL)
    print(
        Fore.BLUE
        + "  load_dotenv()  # This loads the variables from .env into os.environ"
        + Style.RESET_ALL,
    )
    print(Fore.BLUE + "  api_key = os.getenv('BYBIT_API_KEY')" + Style.RESET_ALL)
    print(Fore.BLUE + "  api_secret = os.getenv('BYBIT_API_SECRET')" + Style.RESET_ALL)

    print(Fore.CYAN + "\n## Pyrmethus's Recommendation:" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "  For local development and testing in Termux, the "
        + Fore.YELLOW
        + ".env` file method"
        + Fore.WHITE
        + " is often more convenient."
        "  It keeps your project's configuration self-contained. However, for production deployments"
        "  or automated scripts, setting "
        + Fore.YELLOW
        + "environment variables directly"
        + Fore.WHITE
        + " (e.g., via Termux's startup scripts"
        "  or your job scheduler) is generally more robust and secure."
        + Style.RESET_ALL,
    )
    print(
        Fore.MAGENTA
        + "\n# The secrets are now veiled, and your API keys are safe from prying eyes!\n"
        + Style.RESET_ALL,
    )


if __name__ == "__main__":
    explain_api_key_management()
