import asyncio
from config import Config
from market_maker import MarketMaker
from backtest import MarketMakerBacktester, BacktestParams # Updated import
from datetime import datetime, timezone


async def main():
    """Main entry point for running the bot."""
    config = Config()
    market_maker = MarketMaker(config)

    if config.USE_WEBSOCKET:
        print("Starting Market Maker in LIVE mode with WebSocket...")
        await (
            market_maker.run()
        )  # Run the live bot, which handles its own WebSocket connections
    else:
        print("Starting Market Maker in BACKTEST mode...")
        start_date = datetime.strptime(config.START_DATE, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        end_date = datetime.strptime(config.END_DATE, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )

        # Create BacktestParams
        params = BacktestParams(
            symbol=config.SYMBOL,
            category=config.CATEGORY,
            interval=config.INTERVAL,
            start=start_date,
            end=end_date,
            testnet=config.TESTNET,
            maker_fee=config.MAKER_FEE,
            volume_cap_ratio=config.SLIPPAGE,  # Note: Using SLIPPAGE from config as volume_cap_ratio for backtest. Adjust if needed.
            # sl_tp_emulation is True by default in BacktestParams
        )

        # Instantiate and run the backtester
        backtester = MarketMakerBacktester(
            params, cfg=config
        )  # Pass config to backtester
        results = backtester.run()

        if results:
            print("Backtest Summary:")
            for key, value in results.items():
                print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
