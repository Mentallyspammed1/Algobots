from colorama import Fore
from colorama import Style
from colorama import init

init(autoreset=True)


def explain_unified_margin_vs_standard_account():
    print(
        Fore.MAGENTA
        + "\n# Unveiling the distinctions between Bybit v5 Unified Margin Account and Standard Account...\n"
        + Style.RESET_ALL
    )

    print(Fore.CYAN + "## The Standard Account: A Simpler Path" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "  The Standard Account is Bybit's traditional account type. It operates with separate wallets for different products:"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Spot Wallet:** For spot trading (buying/selling cryptocurrencies directly)."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Derivatives Wallet:** For inverse perpetual, USDT perpetual, and inverse futures trading."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **USDC Derivatives Wallet:** For USDC perpetual and USDC options trading."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Earn Account:** For staking, savings, etc."
        + Style.RESET_ALL
    )
    print(
        Fore.YELLOW + "  ### Key Characteristics of Standard Account:" + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Segregated Funds:** Funds are isolated across different product lines. Margin for derivatives is calculated independently for each product."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Simpler for Beginners:** Easier to understand for new users as each product has its own balance and risk management."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Limited Cross-Collateral:** You cannot use collateral from one product (e.g., Spot) to cover margin requirements in another (e.g., Derivatives) directly."
        + Style.RESET_ALL
    )

    print(
        Fore.CYAN
        + "\n## The Unified Margin Account (UMA): A Holistic Approach"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  The Unified Margin Account is Bybit's advanced account system designed for professional traders. It consolidates funds and margin across multiple products:"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Single Wallet:** All assets (USDT, USDC, BTC, ETH, etc.) are held in a single wallet."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Cross-Collateral:** You can use any supported asset in your UMA as collateral for trading across Spot, USDT Perpetual, USDC Perpetual, and USDC Options."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Unified Margin Calculation:** Margin requirements and risk are calculated across all positions in the UMA, allowing for more efficient capital utilization."
        + Style.RESET_ALL
    )
    print(
        Fore.YELLOW
        + "  ### Key Characteristics of Unified Margin Account:"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Capital Efficiency:** Use your entire portfolio as collateral, potentially reducing liquidation risk and freeing up capital."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Complex Risk Management:** Requires a deeper understanding of cross-margin and portfolio risk. Liquidation of one position can impact others."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Auto-Borrow Feature:** If you open a position that requires a currency you don't hold, the system can automatically borrow it (with interest)."
        + Style.RESET_ALL
    )

    print(
        Fore.CYAN + "\n## Why One Might Be Preferred for Automation:" + Style.RESET_ALL
    )
    print(
        Fore.YELLOW
        + "  ### Unified Margin Account (UMA) is generally preferred for automation due to:"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Enhanced Capital Efficiency:** Automated strategies often benefit from maximizing capital utilization. UMA allows you to deploy capital more flexibly across different trading pairs and products without manual transfers."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Simplified Fund Management:** For a bot managing multiple strategies or positions across various products, a single wallet simplifies balance checks and fund allocation logic."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Reduced Liquidation Risk (Potentially):** By pooling collateral, a temporary dip in one asset might be offset by gains or collateral in another, potentially preventing premature liquidation of individual positions (though it also means a larger, single point of failure if not managed carefully)."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Flexibility for Complex Strategies:** Strategies involving hedging across different products (e.g., spot and perpetuals) or using options can be more seamlessly executed within a UMA."
        + Style.RESET_ALL
    )

    print(
        Fore.YELLOW
        + "  ### When Standard Account might be preferred for automation:"
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Simplicity for Single-Product Bots:** If your bot only trades spot or only one type of derivative, the Standard Account's segregated nature might be simpler to manage and understand the risk for that specific product."
        + Style.RESET_ALL
    )
    print(
        Fore.WHITE
        + "  - **Isolated Risk:** For strategies where you want strict isolation of risk between different trading activities, the Standard Account provides that separation by default."
        + Style.RESET_ALL
    )

    print(Fore.CYAN + "\n## Pyrmethus's Counsel:" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "  For most advanced automated trading strategies on Bybit v5, especially those involving multiple products or complex margin calculations, the "
        + Fore.YELLOW
        + "Unified Margin Account"
        + Fore.WHITE
        + " offers significant advantages in capital efficiency and operational simplicity. However, it demands a more sophisticated understanding of overall portfolio risk management."
        + Style.RESET_ALL
    )

    print(
        Fore.MAGENTA
        + "\n# The scrolls of account types have been unrolled! Choose your path wisely.\n"
        + Style.RESET_ALL
    )


if __name__ == "__main__":
    explain_unified_margin_vs_standard_account()
