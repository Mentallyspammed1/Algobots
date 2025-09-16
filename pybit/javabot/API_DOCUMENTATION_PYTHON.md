# Python Bybit Trader API Documentation

This document provides API documentation for the `BybitTrader` class, the core of the Python-based trading bot.

## `BybitTrader` Class

The `BybitTrader` class orchestrates the trading bot's operations, including loading strategies, connecting to Bybit, and managing orders.

### Initialization

To get started, create an instance of the `BybitTrader` class, providing the path to your strategy file.

**Parameters:**

| Name            | Type     | Description                                      |
| :-------------- | :------- | :----------------------------------------------- |
| `strategy_path` | `string` | The file path to the Python strategy to be loaded. |

**Example:**

```python
from bybit_trader import BybitTrader

# Path to your strategy file
strategy_file = "strategies/my_awesome_strategy.py"

# Initialize the trader
trader = BybitTrader(strategy_path=strategy_file)
```

### Starting the Bot

Once the `BybitTrader` is initialized, you can start the bot using the `start()` method.

#### `start()`

**Description:** Starts the trading bot. This method will:
1.  Fetch initial historical kline data.
2.  Subscribe to the real-time kline WebSocket stream.
3.  Enter a loop to run the strategy and manage the WebSocket connection.

**Example:**

```python
# Start the bot's main loop
trader.start()
```

---

## Public Methods

While you typically only need to use `__init__` and `start()`, the `BybitTrader` class has other public methods that are used internally and can be useful for more advanced use cases.

### `get_historical_klines(symbol, interval)`

**Description:** Fetches historical kline data to bootstrap the bot's internal DataFrame.

**Parameters:**

| Name       | Type     | Description                               | Default |
| :--------- | :------- | :---------------------------------------- | :------ |
| `symbol`   | `string` | The trading pair symbol (e.g., "BTCUSDT"). |         |
| `interval` | `string` | The kline interval (e.g., "1", "5", "D"). | "1"     |

### `run_strategy()`

**Description:** Executes the loaded strategy's `generate_signals()` method and places orders based on the returned signals.

### `place_order(side)`

**Description:** Places a market order on Bybit. It also handles closing existing positions before opening a new one and includes a cooldown period.

**Parameters:**

| Name   | Type     | Description                      |
| :----- | :------- | :------------------------------- |
| `side` | `string` | The order side: "Buy" or "Sell". |
