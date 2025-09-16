# Creating a Custom Trading Strategy

This tutorial guides you through creating your own custom trading strategies for both the Node.js and Python environments. The modular design allows you to easily extend the bot's functionality.

## Node.js Strategy Tutorial

Node.js strategies are located in the `strategies/` directory within the `javabot` folder. Each strategy is a JavaScript module that exports a class with a `generateSignals` method.

### Basic Structure

A Node.js strategy class should extend a base strategy (if available, otherwise implement the required methods) and implement a `generateSignals` method.

```javascript
// strategies/my_custom_strategy.js
import { BaseStrategy } from './base_strategy.js'; // Assuming a BaseStrategy exists

class MyCustomStrategy extends BaseStrategy {
    constructor() {
        super('MyCustomStrategy'); // Name your strategy
        this.someParameter = 10; // Define strategy-specific parameters
    }

    /**
     * Generates trading signals based on kline data.
     * @param {Array<Object>} klines - An array of kline objects (OHLCV data).
     * @returns {string} The trading signal: 'buy', 'sell', or 'hold'.
     */
    generateSignals(klines) {
        // Implement your custom logic here
        // Example: Simple moving average crossover
        if (klines.length < this.someParameter) {
            return 'hold'; // Not enough data
        }

        const lastClose = klines[klines.length - 1].close;
        const prevClose = klines[klines.length - 2].close;

        if (lastClose > prevClose) {
            return 'buy';
        } else if (lastClose < prevClose) {
            return 'sell';
        }
        return 'hold';
    }
}

export default MyCustomStrategy;
```

### Step-by-Step Example: Simple Moving Average Crossover

1.  **Create a new file:** In the `javabot/strategies/` directory, create a new file named `sma_crossover_strategy.js`.

2.  **Implement the strategy logic:**

    ```javascript
    // javabot/strategies/sma_crossover_strategy.js
    import { BaseStrategy } from './base_strategy.js'; // Adjust path if needed

    class SMACrossoverStrategy extends BaseStrategy {
        constructor() {
            super('SMACrossoverStrategy');
            this.shortPeriod = 10;
            this.longPeriod = 30;
        }

        calculateSMA(klines, period) {
            if (klines.length < period) {
                return null;
            }
            const sum = klines.slice(-period).reduce((acc, k) => acc + k.close, 0);
            return sum / period;
        }

        generateSignals(klines) {
            if (klines.length < this.longPeriod) {
                return 'hold'; // Not enough data for long SMA
            }

            const shortSMA = this.calculateSMA(klines, this.shortPeriod);
            const longSMA = this.calculateSMA(klines, this.longPeriod);

            if (shortSMA > longSMA && klines[klines.length - 2].close <= klines[klines.length - 2].open) { // Buy signal
                return 'buy';
            } else if (shortSMA < longSMA && klines[klines.length - 2].close >= klines[klines.length - 2].open) { // Sell signal
                return 'sell';
            }
            return 'hold';
        }
    }

    export default SMACrossoverStrategy;
    ```

3.  **Integrate with `config.js`:** Open `javabot/config.js` and add your new strategy to the `STRATEGIES` object:

    ```javascript
    export const CONFIG = {
        // ... other configurations
        STRATEGIES: {
            // ... existing strategies
            sma_crossover_strategy: {
                enabled: true,
                symbol: 'ETHUSDT',
                interval: '5', // 5-minute klines
                leverage: 20,
                // Add any custom parameters for your strategy here
            },
        },
    };
    ```

## Python Strategy Tutorial

Python strategies are located in the `strategies/` directory within the repository root. Each strategy is a Python file that defines a class inheriting from `BaseStrategy` and implements a `generate_signals` method.

### Basic Structure

A Python strategy class must inherit from `BaseStrategy` and implement the `generate_signals` method.

```python
# strategies/my_custom_strategy.py
import pandas as pd
# import any necessary libraries for indicators (e.g., pandas_ta, talib)
from strategies.base_strategy import BaseStrategy

class MyCustomStrategy(BaseStrategy):
    def __init__(self):
        super().__init__("MyCustomStrategy") # Name your strategy
        self.some_parameter = 10 # Define strategy-specific parameters

    def generate_signals(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """
        Generates trading signals based on OHLCV data.
        Args:
            dataframe (pd.DataFrame): DataFrame with OHLCV data.
        Returns:
            pd.DataFrame: DataFrame with 'signal' column ('buy', 'sell', or 'hold').
        """
        df = dataframe.copy()

        # Implement your custom logic here
        # Example: Simple price action
        if len(df) < 2:
            df['signal'] = 'hold'
            return df

        last_close = df['close'].iloc[-1]
        prev_close = df['close'].iloc[-2]

        if last_close > prev_close:
            df.loc[df.index[-1], 'signal'] = 'buy'
        elif last_close < prev_close:
            df.loc[df.index[-1], 'signal'] = 'sell'
        else:
            df.loc[df.index[-1], 'signal'] = 'hold'

        return df
```

### Step-by-Step Example: MACD Crossover Strategy

1.  **Create a new file:** In the `strategies/` directory (repository root), create a new file named `macd_crossover_strategy.py`.

2.  **Implement the strategy logic:**

    ```python
    # strategies/macd_crossover_strategy.py
    import pandas as pd
    import pandas_ta as ta # Assuming pandas_ta is installed
    from strategies.base_strategy import BaseStrategy

    class MACDCrossoverStrategy(BaseStrategy):
        def __init__(self):
            super().__init__("MACDCrossoverStrategy")
            self.fast_period = 12;
            self.slow_period = 26;
            self.signal_period = 9;

        def generate_signals(self, dataframe: pd.DataFrame) -> pd.DataFrame:
            df = dataframe.copy()

            # Calculate MACD
            macd_data = ta.macd(df['close'], fast=self.fast_period, slow=self.slow_period, signal=self.signal_period)
            df['MACD'] = macd_data[f'MACD_{self.fast_period}_{self.slow_period}_{self.signal_period}']
            df['MACD_signal'] = macd_data[f'MACDs_{self.fast_period}_{self.slow_period}_{self.signal_period}']

            df['signal'] = 'hold'

            if len(df) > self.slow_period: # Ensure enough data for MACD calculation
                # Generate buy signal: MACD crosses above MACD_signal
                if df['MACD'].iloc[-2] < df['MACD_signal'].iloc[-2] and df['MACD'].iloc[-1] > df['MACD_signal'].iloc[-1]:
                    df.loc[df.index[-1], 'signal'] = 'buy'
                # Generate sell signal: MACD crosses below MACD_signal
                elif df['MACD'].iloc[-2] > df['MACD_signal'].iloc[-2] and df['MACD'].iloc[-1] < df['MACD_signal'].iloc[-1]:
                    df.loc[df.index[-1], 'signal'] = 'sell'

            return df
    ```

3.  **Integrate with `config.py`:** Open `config.py` (repository root) and update the `STRATEGY_FILE` variable to point to your new strategy:

    ```python
    # config.py
    # ... other configurations
    STRATEGY_FILE = "strategies/macd_crossover_strategy.py"
    ```
