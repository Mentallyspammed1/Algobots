# main.py
import logging
import os

from integration.strategy_factory import StrategyFactory
from pybit.unified_trading import HTTP

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ChandelierEhlersBot")


class ChandelierEhlersBot:
    """Main application class for the Chandelier Exit Ehlers SuperTrend trading bot."""

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """Initialize the trading bot."""
        # Initialize API session
        self.session = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret)

        # Strategy configuration
        self.strategy_config = {
            "chandelier_period": 22,
            "chandelier_multiplier": 3.0,
            "supertrend_period": 10,
            "supertrend_multiplier": 3.0,
            "min_signal_strength": 0.5,
            "min_signal_confidence": 0.6,
            "timeframe": "15",
            "data_limit": 200,
            "symbols": ["BTCUSDT", "ETHUSDT"],
        }

        # Create strategy instance
        self.strategy = StrategyFactory.create_chandelier_ehlers_strategy(
            self.strategy_config, self.session,
        )

        logger.info("Initialized Chandelier Exit Ehlers SuperTrend trading bot")

    def run(self):
        """Run the trading bot."""
        logger.info("Starting trading bot...")

        try:
            # Generate signals
            signals = self.strategy.generate_signals(self.strategy_config["symbols"])

            # Process signals
            for signal in signals:
                logger.info(
                    f"Generated signal: {signal.type} for {signal.symbol} "
                    f"at {signal.price}",
                )
                logger.info(f"Reasons: {signal.reasons}")
                logger.info(f"Indicators: {signal.indicators}")
                logger.info(
                    f"Strength: {signal.strength}, Confidence: {signal.confidence}",
                )

                # Here you would add code to execute trades based on signals
                # For example:
                # if signal.type == "BUY":
                #     self.execute_buy_order(signal)
                # elif signal.type == "SELL":
                #     self.execute_sell_order(signal)

            logger.info("Trading cycle completed")

        except Exception as e:
            logger.error(f"Error in trading cycle: {e!s}")

    def get_indicator_values(self, symbol: str) -> dict:
        """Get current indicator values for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Dictionary with current indicator values

        """
        return self.strategy.get_indicator_values(symbol)


if __name__ == "__main__":
    # Example usage
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")

    bot = ChandelierEhlersBot(api_key, api_secret, testnet=True)

    # Run the bot
    bot.run()

    # Get indicator values for a symbol
    indicator_values = bot.get_indicator_values("BTCUSDT")
    print(f"Current indicator values for BTCUSDT: {indicator_values}")
