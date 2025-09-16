
## Advanced Order Types

### Conditional Orders with Take Profit and Stop Loss

Conditional orders are triggered when a specified price (`triggerPrice`) is met. You can attach Take Profit (TP) and Stop Loss (SL) directly to this order.

```python
import os
from pybit.unified_trading import HTTP

# Replace with your actual API key and secret, or load from environment variables
api_key = "YOUR_API_KEY"
api_secret = "YOUR_API_SECRET"

# Initialize the HTTP session for the Bybit Unified Trading Account (UTA)
# Set testnet=True for testing on the Bybit testnet.
session = HTTP(
    testnet=True,
    api_key=api_key,
    api_secret=api_secret
)

def place_conditional_order_with_tpsl(
    symbol: str,
    side: str,
    order_type: str,
    qty: str,
    price: str, # Required for Limit orders
    trigger_price: str,
    trigger_direction: int, # 1 for triggerPrice > market price, 2 for triggerPrice < market price
    take_profit: str = None,
    stop_loss: str = None,
    tp_trigger_by: str = "MarkPrice", # LastPrice, MarkPrice, IndexPrice
    sl_trigger_by: str = "MarkPrice", # LastPrice, MarkPrice, IndexPrice
    category: str = "linear"
):
    """
    Places a conditional order with optional Take Profit and Stop Loss.
    """
    try:
        params = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
            "triggerPrice": trigger_price,
            "triggerDirection": trigger_direction,
            "orderFilter": "ConditionalOrder", # Indicates a conditional order
            "timeInForce": "GTC" # Good-Till-Canceled
        }

        if order_type == "Limit":
            params["price"] = price

        if take_profit:
            params["takeProfit"] = take_profit
            params["tpTriggerBy"] = tp_trigger_by
        if stop_loss:
            params["stopLoss"] = stop_loss
            params["slTriggerBy"] = sl_trigger_by

        response = session.place_order(**params)
        print(f"Conditional Order Response: {response}")
        return response
    except Exception as e:
        print(f"Error placing conditional order: {e}")
        return None

# Example Usage:
# Place a conditional BUY limit order for BTCUSDT (linear)
# Triggered when price reaches 30000, then places a limit order at 29900.
# Includes TP at 31000 and SL at 29000.
# Note: Ensure triggerDirection is correct based on your triggerPrice relative to current market price.
# For a buy order triggered when price goes up, triggerDirection is 1.
# For a sell order triggered when price goes down, triggerDirection is 2.
# For a buy order triggered when price goes down (e.g., for a bounce), triggerDirection is 2.
# For a sell order triggered when price goes up (e.g., for a reversal), triggerDirection is 1.

# place_conditional_order_with_tpsl(
#     symbol="BTCUSDT",
#     side="Buy",
#     order_type="Limit",
#     qty="0.001",
#     price="29900",
#     trigger_price="30000",
#     trigger_direction=1, # Trigger when price goes above 30000
#     take_profit="31000",
#     stop_loss="29000"
# )

# Example 2: Sell BTCUSDT if price breaks below 28000, place market order, with TP/SL
# (Assuming current price is above 28000)
# place_conditional_order_with_tpsl(
#     symbol="BTCUSDT",
#     side="Sell",
#     order_type="Market",
#     qty="0.001",
#     price=None, # Not required for Market orders
#     trigger_price="28000",
#     trigger_direction=2, # Trigger when price goes below 28000
#     take_profit="27000",
#     stop_loss="29000"
# )
```

### Batch Orders

The `place_batch_order` endpoint allows you to send multiple order requests in a single API call. This is efficient for placing several orders simultaneously.

```python
def place_batch_orders(orders: list, category: str = "linear"):
    """
    Places a batch of orders.
    Each order in the list should be a dictionary with order parameters.
    """
    try:
        payload = {
            "category": category,
            "request": orders
        }
        response = session.place_batch_order(**payload)
        print(f"Batch Order Response: {response}")
        return response
    except Exception as e:
        print(f"Error placing batch orders: {e}")
        return None

# Example Usage:
# Place two limit orders for BTCUSDT and ETHUSDT in a single batch.
batch_order_requests = [
    {
        "symbol": "BTCUSDT",
        "side": "Buy",
        "orderType": "Limit",
        "qty": "0.001",
        "price": "29500",
        "timeInForce": "GTC",
        "orderLinkId": "batch-order-btc-1" # Optional: Custom client order ID
    },
    {
        "symbol": "ETHUSDT",
        "side": "Sell",
        "orderType": "Limit",
        "qty": "0.01",
        "price": "1800",
        "timeInForce": "GTC",
        "orderLinkId": "batch-order-eth-1"
    }
]

# place_batch_orders(batch_order_requests, category="linear")
```

### Setting Take Profit and Stop Loss for an Existing Position

If you already have an open position, you can set or modify its TP/SL using the `set_trading_stop` method.

```python
def set_position_tpsl(
    symbol: str,
    take_profit: str = None,
    stop_loss: str = None,
    tp_trigger_by: str = "MarkPrice",
    sl_trigger_by: str = "MarkPrice",
    position_idx: int = 0, # 0 for one-way mode, 1 for buy-hedge, 2 for sell-hedge
    category: str = "linear",
    tpsl_mode: str = "Full", # "Full" or "Partial"
    tp_size: str = None, # Required for Partial mode
    sl_size: str = None, # Required for Partial mode
    tp_order_type: str = "Market", # Market or Limit
    sl_order_type: str = "Market", # Market or Limit
    tp_limit_price: str = None, # Required if tp_order_type is Limit
    sl_limit_price: str = None # Required if sl_order_type is Limit
):
    """
    Sets or modifies Take Profit and Stop Loss for an existing position.
    """
    try:
        params = {
            "category": category,
            "symbol": symbol,
            "positionIdx": position_idx,
            "tpslMode": tpsl_mode
        }

        if take_profit:
            params["takeProfit"] = take_profit
            params["tpTriggerBy"] = tp_trigger_by
            if tpsl_mode == "Partial":
                params["tpSize"] = tp_size
                params["tpOrderType"] = tp_order_type
                if tp_order_type == "Limit":
                    params["tpLimitPrice"] = tp_limit_price

        if stop_loss:
            params["stopLoss"] = stop_loss
            params["slTriggerBy"] = sl_trigger_by
            if tpsl_mode == "Partial":
                params["slSize"] = sl_size
                params["slOrderType"] = sl_order_type
                if sl_order_type == "Limit":
                    params["slLimitPrice"] = sl_limit_price

        response = session.set_trading_stop(**params)
        print(f"Set TP/SL Response: {response}")
        return response
    except Exception as e:
        print(f"Error setting TP/SL: {e}")
        return None

# Example Usage:
# Assuming you have an open long position on BTCUSDT (linear)
# Set TP at 31500 and SL at 28500 for the full position.
# set_position_tpsl(
#     symbol="BTCUSDT",
#     take_profit="31500",
#     stop_loss="28500",
#     tp_trigger_by="MarkPrice",
#     sl_trigger_by="MarkPrice",
#     category="linear",
#     tpsl_mode="Full"
# )

# Example: Set partial TP for 50% of position
# set_position_tpsl(
#     symbol="BTCUSDT",
#     take_profit="31000",
#     tp_trigger_by="MarkPrice",
#     category="linear",
#     tpsl_mode="Partial",
#     tp_size="0.0005", # Half of 0.001 BTC
#     tp_order_type="Limit",
#     tp_limit_price="30950"
# )
