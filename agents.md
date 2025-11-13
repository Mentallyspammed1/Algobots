# WhaleBot Agents
This document outlines the technical indicators and analysis methods employed by the WhaleBot trading bot.

## Core Logic
WhaleBot analyzes market data to identify potential trading opportunities. It uses a combination of technical indicators, order book analysis, and configurable weighting systems to generate signals. The bot aims to adapt to market volatility by dynamically selecting indicator weights.

## Technical Indicators Supported

### Trend and Momentum Indicators

*   **EMA Alignment:** Checks for consistent alignment between short-term and long-term Exponential Moving Averages (EMAs) and the price, indicating trend strength.
*   **Momentum:** Measures the rate of price change, often used with moving averages to identify trend direction and potential reversals.
    *   Uses short and long-term Moving Averages (MA) of the momentum indicator.
*   **MACD (Moving Average Convergence Divergence):** Analyzes the relationship between two EMAs of price to identify shifts in momentum.
    *   Includes MACD line, Signal line, and Histogram.
*   **ADX (Average Directional Index):** Measures trend strength, not direction. Higher values indicate a stronger trend.

### Oscillators and Volatility Indicators

*   **RSI (Relative Strength Index):** A momentum oscillator that measures the speed and change of price movements. Used to identify overbought or oversold conditions.
*   **Stochastic RSI:** Applies the stochastic oscillator calculation to RSI values, providing a more sensitive measure of overbought/oversold conditions and potential crossovers.
    *   Includes %K (fast line) and %D (slow line).
*   **CCI (Commodity Channel Index):** Measures the current price level relative to an average over a period, indicating overbought or oversold conditions.
*   **Williams %R:** Similar to the Stochastic Oscillator, it measures overbought/oversold levels based on closing price relative to the trading range.
*   **ATR (Average True Range):** Measures market volatility by decomposing the entire range of an asset price for that period.
*   **MFI (Money Flow Index):** Similar to RSI but incorporates volume, measuring buying and selling pressure.

### Volume and Accumulation Indicators

*   **Volume Confirmation:** Checks if current trading volume is significantly higher than its moving average, confirming the strength of a price move.
*   **OBV (On-Balance Volume):** Relates price and volume by adding volume on up days and subtracting volume on down days.
*   **ADI (Accumulation/Distribution Index):** Measures the cumulative flow of money into and out of a security, using closing price relative to its high-low range and volume.

### Other Indicators

*   **PSAR (Parabolic Stop and Reverse):** A time and price based trading tool used to identify potential reversals.
*   **FVE (Fictional Value Estimate):** A custom composite indicator combining price momentum, volume strength, and volatility (inverse ATR).

## Advanced Analysis

*   **Divergence Detection:** Identifies potential trend reversals when price moves in one direction, but a momentum indicator (like MACD) moves in the opposite direction.
*   **Order Book Analysis:** Analyzes the order book for significant bid (support) and ask (resistance) "walls" based on volume thresholds, providing insights into immediate supply and demand.
*   **Support and Resistance Levels:** Calculates Fibonacci retracement and Pivot Point levels to identify potential price barriers.

## Configuration and Adaptability

*   **Configurable Indicators:** Users can enable or disable specific indicators via `config.json`.
*   **Dynamic Weighting:** The bot adjusts the importance (weight) of different indicators based on market volatility (detected via ATR), using predefined `low_volatility` and `high_volatility` sets.
*   **Signal Score Threshold:** A minimum combined weight score from active indicators is required to generate a valid trading signal.
*   **Cooldown Periods:** Implements cooldowns for signal generation and order book API calls to prevent excessive trading and API abuse.
*   **Stop Loss and Take Profit:** Automatically suggests SL/TP levels based on ATR multiples, adjustable in the configuration.

## Logging

The bot maintains detailed logs in the `bot_logs/` directory, with separate log files for each trading symbol, capturing all analysis steps, indicator values, and trading signals.

## Disclaimer

This bot is for educational and informational purposes only. It is not financial advice. Trading cryptocurrencies involves significant risk, and you could lose your invested capital. Always conduct your own research and consult with a qualified financial advisor before making any trading decisions.
