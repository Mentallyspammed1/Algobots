
import asyncio
from config import Config
from market_maker import MarketMaker
from backtester import BacktestEngine

async def main():
    """Main entry point for running the backtester."""
    config = Config()
    market_maker = MarketMaker()
    market_maker.session = None  # Disable live trading

    backtester = BacktestEngine(market_maker, config)
    results = await backtester.run_backtest()
    
    if results:
        backtester.save_results()

if __name__ == "__main__":
    asyncio.run(main())
