#!/usr/bin/env python3
"""Advanced Bybit V5 Market Maker Bot
Main entry point for the application
"""

import argparse
import signal
import sys
from datetime import datetime

from market_maker import MarketMaker

from utils import load_config, load_env_variables, setup_logger


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    print("\nReceived shutdown signal. Closing bot...")
    sys.exit(0)


def validate_config(config: dict, env_config: dict) -> bool:
    """Validate configuration before starting"""
    logger = setup_logger("ConfigValidator")

    # Check API credentials
    if not env_config["api_key"] or not env_config["api_secret"]:
        logger.error("API credentials not found in .env file")
        return False

    # Check required config sections
    required_sections = ["trading", "risk_management", "execution", "monitoring"]
    for section in required_sections:
        if section not in config:
            logger.error(f"Missing required config section: {section}")
            return False

    # Validate trading parameters
    if config["trading"]["order_amount"] <= 0:
        logger.error("Invalid order amount")
        return False

    if config["trading"]["num_orders"] <= 0:
        logger.error("Invalid number of orders")
        return False

    logger.info("Configuration validation passed")
    return True


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Bybit Market Maker Bot")
    parser.add_argument(
        "--config", type=str, default="config.yaml", help="Path to configuration file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in simulation mode without placing real orders",
    )
    args = parser.parse_args()

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Load configurations
    print("=" * 50)
    print("BYBIT MARKET MAKER BOT V2.0")
    print("=" * 50)
    print(f"Starting at {datetime.now()}")
    print(f"Loading configuration from {args.config}")

    try:
        config = load_config(args.config)
        env_config = load_env_variables()

        # Validate configuration
        if not validate_config(config, env_config):
            print("Configuration validation failed. Exiting...")
            sys.exit(1)

        # Override for dry run
        if args.dry_run:
            print("WARNING: Running in DRY RUN mode - no real orders will be placed")
            env_config["environment"] = "testnet"

        # Initialize and run market maker
        market_maker = MarketMaker(config, env_config)

        print(f"Environment: {env_config['environment'].upper()}")
        print(f"Symbol: {config['trading']['symbol']}")
        print(f"Strategy: {config['advanced']['strategy_type']}")
        print("=" * 50)
        print("Bot initialization complete. Starting trading...")
        print("Press Ctrl+C to stop")
        print("=" * 50)

        # Start the bot
        market_maker.run()

    except FileNotFoundError as e:
        print(f"Error: Configuration file not found - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
