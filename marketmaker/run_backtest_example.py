from datetime import datetime, timezone

from backtest import run_backtest
from market_maker import MarketMaker  # adjust import

if __name__ == "__main__":
    bot = MarketMaker()  # Uses your Config; session set to None by backtester

    start = datetime(2025, 7, 1, tzinfo=timezone.utc)
    end   = datetime(2025, 7, 15, tzinfo=timezone.utc)

    ec = run_backtest(
        bot=bot,
        category=bot.config.CATEGORY,   # e.g., "linear" for USDT perps
        symbol=bot.config.SYMBOL,       # e.g., "BTCUSDT"
        interval="1",                   # 1-minute klines
        start=start,
        end=end,
        testnet=bot.config.TESTNET,
        initial_cash=10_000.0,
        maker_fee=0.0001,               # adjust per your fee tier
        taker_fee=0.0006,
        slippage_bps=0.0,
    )

    print(ec.tail())
    print("Final equity:", ec['equity'].iloc[-1])
