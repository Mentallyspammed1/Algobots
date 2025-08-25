# market_making_strategy.py

import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Any

import numpy as np
from pybit.unified_trading import HTTP

logger = logging.getLogger(__name__)

async def market_making_strategy(
    market_data: dict[str, Any],
    account_info: dict[str, Any],
    http_client: HTTP,
    bot_instance: Any,
    symbols: list[str],
    config: dict[str, Any]
):
    logger.info("-" * 50)
    logger.info(f"Executing Market Making Strategy at {datetime.now()}")
    base_currency = bot_instance.base_currency
    for wallet_entry in account_info.get('list', []):
        for coin_info in wallet_entry.get('coin', []):
            if coin_info.get('coin') == base_currency:
                logger.info(f"{base_currency} Balance: Available={coin_info.get('availableToWithdraw')}, Total={coin_info.get('walletBalance')}")
                break
    for symbol in symbols:
        logger.info(f"Processing symbol: {symbol}")
        symbol_market_data = market_data.get(symbol)
        if not symbol_market_data:
            logger.warning(f"  No market data available for {symbol}. Skipping.")
            continue
        orderbook = symbol_market_data.get("orderbook", {})
        ticker = symbol_market_data.get("ticker", {})
        bids = orderbook.get('b', [])
        asks = orderbook.get('a', [])
        best_bid_price = Decimal(bids[0][0]) if bids and bids[0] else Decimal('0')
        best_ask_price = Decimal(asks[0][0]) if asks and asks[0] else Decimal('0')
        last_price = Decimal(ticker.get('lastPrice', '0')) if ticker else Decimal('0')
        logger.info(f"  {symbol} - Last Price: {last_price}, Best Bid: {best_bid_price}, Best Ask: {best_ask_price}")
        position_data = bot_instance.ws_manager.positions.get(symbol, {})
        current_position_size = Decimal(position_data.get('size', '0'))
        position_side = position_data.get('side', 'None')
        logger.info(f"  Current position for {symbol}: {position_side} {current_position_size}")
        klines_data = await bot_instance.get_historical_klines(symbol, "1", limit=100)
        volatility = Decimal('0.01')
        if klines_data and klines_data.get('result', {}).get('list'):
            closes = [Decimal(k[4]) for k in klines_data.get('result', {}).get('list', [])]
            if len(closes) > 1:
                returns = np.diff([float(c) for c in closes]) / [float(c) for c in closes[:-1]]
                volatility = Decimal(np.std(returns))
                logger.info(f"  Volatility for {symbol}: {volatility:.4f}")

        base_spread = Decimal(config.get("BASE_SPREAD", '0.001'))
        adjusted_spread = base_spread * (Decimal('1') + volatility * Decimal('10'))
        inventory_skew = Decimal('0')
        max_inventory_units = Decimal(config.get("MAX_INVENTORY_UNITS", "10"))
        if current_position_size != 0:
            inventory_skew = (current_position_size / max_inventory_units) * adjusted_spread

        if abs(current_position_size) < max_inventory_units and best_bid_price > 0 and best_ask_price > 0:
            if bot_instance.get_open_positions_count() < bot_instance.max_open_positions:
                capital_percentage_per_order = Decimal(config.get("ORDER_CAPITAL_PERCENTAGE", "0.0001"))
                buy_qty = await bot_instance.calculate_position_size(symbol, float(capital_percentage_per_order), best_bid_price, account_info)
                if buy_qty > 0:
                    limit_buy_price = bot_instance._round_to_tick_size(symbol, best_bid_price * (Decimal('1') - adjusted_spread - inventory_skew))
                    if limit_buy_price > 0:
                        await bot_instance.place_order(
                            symbol=symbol,
                            side="Buy",
                            order_type="Limit",
                            qty=buy_qty,
                            price=limit_buy_price,
                            time_in_force="PostOnly",
                            orderLinkId=f"mm_buy_{int(time.time() * 1000)}_{symbol}"
                        )

                sell_qty = await bot_instance.calculate_position_size(symbol, float(capital_percentage_per_order), best_ask_price, account_info)
                if sell_qty > 0:
                    limit_sell_price = bot_instance._round_to_tick_size(symbol, best_ask_price * (Decimal('1') + adjusted_spread + inventory_skew))
                    if limit_sell_price > 0:
                        await bot_instance.place_order(
                            symbol=symbol,
                            side="Sell",
                            order_type="Limit",
                            qty=sell_qty,
                            price=limit_sell_price,
                            time_in_force="PostOnly",
                            orderLinkId=f"mm_sell_{int(time.time() * 1000)}_{symbol}"
                        )
        elif current_position_size.abs() >= max_inventory_units:
            logger.warning(f"  Inventory limit reached for {symbol}. Closing position.")
            close_side = "Sell" if position_side == "Buy" else "Buy"
            await bot_instance.place_order(symbol, close_side, "Market", current_position_size.abs())

        for order_id, order in list(bot_instance.ws_manager.orders.items()):
            if order.get('orderStatus') == "New":
                order_creation_time_ms = int(order.get('createdTime', 0))
                if time.time() * 1000 - order_creation_time_ms > 60000: # 1 minute
                    logger.info(f"  Cancelling stale order {order_id} for {symbol}")
                    await bot_instance.cancel_order(symbol, order_id=order_id)

    logger.info("-" * 50)
