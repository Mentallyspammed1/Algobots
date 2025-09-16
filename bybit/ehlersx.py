import logging
from typing import Any

from pybit.unified_trading import HTTP

logger = logging.getLogger(__name__)

# --- Technical Indicator Functions ---
def calculate_ema(prices: list[float], period: int) -> list[float]:
    """Calculates Exponential Moving Average (EMA).
    This is a standard EMA, used as an "Ehlers-like" MA for this strategy.
    """
    if not prices or len(prices) < period:
        return []

    ema_values = [0.0] * len(prices)
    smoothing_factor = 2 / (period + 1)

    # Calculate initial SMA for the first EMA value
    # Ensure there are enough prices for the initial SMA
    if period > 0:
        ema_values[period - 1] = sum(prices[:period]) / period
    else: # Handle period = 0 case, though it shouldn't happen with validation
        return []

    # Calculate subsequent EMA values
    for i in range(period, len(prices)):
        ema_values[i] = (prices[i] * smoothing_factor) + (ema_values[i-1] * (1 - smoothing_factor))

    return ema_values

# --- Ehlers MA Cross Strategy ---
# Global state to track last signal and position
_last_signal: dict[str, str | None] = {}
_current_position: dict[str, str | None] = {}

async def ehlers_ma_cross_strategy(market_data: dict, account_info: dict, http_client: HTTP, bot_instance: Any, symbols_to_trade: list[str]):
    """Ehlers Moving Average Cross Strategy.
    This strategy uses two standard EMAs (fast and slow) as "Ehlers-like" MAs.
    It generates buy/sell signals based on their crosses.
    
    Args:
        market_data: Dictionary containing current market data.
        account_info: Dictionary containing account balance and position information.
        http_client: An instance of pybit.unified_trading.HTTP for placing orders.
        bot_instance: The BybitTradingBot instance, to access methods like get_historical_klines.
        symbols_to_trade: List of symbols to apply the strategy to.
    """
    logger.info("Executing Ehlers MA Cross Strategy...")

    for symbol in symbols_to_trade: # Iterate over each symbol
        logger.info(f"Applying strategy for {symbol}...")
        fast_ema_period = 9
        slow_ema_period = 21
        trade_quantity = 0.001 # Example quantity

        # Fetch historical Klines (e.g., 1-hour candles)
        klines_data_response = await bot_instance.get_historical_klines(
            symbol=symbol,
            interval="3", # 3-minute candles
            limit=max(fast_ema_period, slow_ema_period) + 5 # Get enough data for EMAs
        )

        if not klines_data_response or klines_data_response['retCode'] != 0:
            logger.warning(f"Failed to fetch klines for {symbol}. Skipping strategy.")
            continue # continue to next symbol

        # Extract closing prices
        # klines_data_response['result']['list'] contains [timestamp, open, high, low, close, volume]
        closing_prices = [float(kline[4]) for kline in klines_data_response['result']['list']]

        if len(closing_prices) < max(fast_ema_period, slow_ema_period):
            logger.warning(f"Not enough historical data for {symbol} to calculate EMAs. Need at least {max(fast_ema_period, slow_ema_period)} periods.")
            continue

        fast_ema = calculate_ema(closing_prices, fast_ema_period)
        slow_ema = calculate_ema(closing_prices, slow_ema_period)

        if not fast_ema or not slow_ema or len(fast_ema) < 2 or len(slow_ema) < 2:
            logger.warning(f"EMA calculation failed or not enough EMA data for {symbol}. Skipping strategy.")
            continue

        # Get the latest EMA values
        latest_fast_ema = fast_ema[-1]
        latest_slow_ema = slow_ema[-1]

        # Get the previous EMA values to detect crosses
        previous_fast_ema = fast_ema[-2]
        previous_slow_ema = slow_ema[-2]

        current_price = float(market_data.get(symbol, {}).get("ticker", [{}])[0].get("lastPrice", 0))
        logger.info(f"Current price for {symbol}: {current_price}")

        # Get current position from bot_instance's ws_manager.positions
        # The bot_instance.ws_manager.positions will be updated by the WebSocket stream
        # It's a dictionary: {symbol: {side: "Long" or "Short", size: Decimal, ...}}
        current_symbol_position_data = bot_instance.ws_manager.positions.get(symbol, {})

        # Determine if we have an open position for the symbol
        has_long_position = False
        has_short_position = False

        if current_symbol_position_data:
            # Check if the position size is greater than 0
            if float(current_symbol_position_data.get('size', 0)) > 0:
                if current_symbol_position_data.get('side') == 'Buy':
                    has_long_position = True
                elif current_symbol_position_data.get('side') == 'Sell':
                    has_short_position = True

        # Determine signal
        signal = None
        if previous_fast_ema <= previous_slow_ema and latest_fast_ema > latest_slow_ema:
            signal = "buy"
            logger.info(f"BUY Signal for {symbol}: Fast EMA ({latest_fast_ema:.5f}) crossed above Slow EMA ({latest_slow_ema:.5f})")
        elif previous_fast_ema >= previous_slow_ema and latest_fast_ema < latest_slow_ema:
            signal = "sell"
            logger.info(f"SELL Signal for {symbol}: Fast EMA ({latest_fast_ema:.5f}) crossed below Slow EMA ({latest_slow_ema:.5f})")
        else:
            logger.info(f"No cross signal for {symbol}. Fast EMA: {latest_fast_ema:.5f}, Slow EMA: {latest_slow_ema:.5f}")

        # Execute trades based on signal and current position
        if signal == "buy":
            if not has_long_position: # Only buy if not already long
                logger.info(f"Attempting to BUY {trade_quantity} {symbol} at {current_price}")
                await bot_instance.place_order(
                    category="linear",
                    symbol=symbol,
                    side="Buy",
                    order_type="Market",
                    qty=trade_quantity
                )
            else:
                logger.info(f"Already in a LONG position for {symbol}. No new buy order.")
        elif signal == "sell":
            if not has_short_position: # Only sell if not already short
                logger.info(f"Attempting to SELL {trade_quantity} {symbol} at {current_price}")
                await bot_instance.place_order(
                    category="linear",
                    symbol=symbol,
                    side="Sell",
                    order_type="Market",
                    qty=trade_quantity
                )
        else:
            logger.info(f"No trading action for {symbol}.")
