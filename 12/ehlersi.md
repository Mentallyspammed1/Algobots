# John Ehlers' Technical Indicators & Calculations

John Ehlers is a pioneer in applying digital signal processing techniques to financial market data. His indicators are known for their responsiveness and ability to identify market cycles.

---

## 1. Ehlers Fisher Transform

The Fisher Transform converts asset prices into a Gaussian normal distribution, which helps in identifying price reversals more clearly.

### Concept:
- It normalizes price movements over a specific period.
- Extreme values (e.g., above +1.5 or below -1.5) are often interpreted as overbought or oversold conditions.
- Crossovers between the Fisher Transform line and its signal line (a moving average of the transform) can be used to generate trading signals.

### Calculation:
The core formula is:
**`Fisher Transform = 0.5 * ln((1 + X) / (1 - X))`**

Where:
- **`ln`** is the natural logarithm.
- **`X`** is the price transformed to a value between -1 and 1 for a given lookback period.

#### Pseudocode:
```python
# period = 10 (typical)
# price = (high + low) / 2

# 1. Find the highest high and lowest low over the lookback period.
# max_high = highest(high, period)
# min_low = lowest(low, period)

# 2. Transform the current price to a value 'X' between -1 and 1.
# Note: Ehlers' formula involves intermediate smoothing. A simplified representation is:
# X = 2 * ((price - min_low) / (max_high - min_low)) - 1

# 3. Apply the Fisher Transform formula.
# fisher = 0.5 * log((1 + X) / (1 - X))

# 4. A signal line is often used for crossover signals.
# signal = moving_average(fisher, 9)
```

---

## 2. Ehlers Stochastic RSI

This indicator applies Ehlers' "Roofing Filter" to the price data before calculating the Stochastic RSI. The goal is to remove high-frequency noise and provide a smoother, more responsive oscillator.

### Concept:
- The Roofing Filter acts as a band-pass filter, removing market noise and short-term volatility.
- The standard Stochastic RSI is then calculated on this "cleaned" data.
- The result is an oscillator that can identify overbought and oversold conditions with fewer false signals.

---

## 3. Ehlers Instantaneous Trendline

This is a responsive trendline that aims to identify the current trend with minimal lag by separating price data into its trend and cyclical components.

### Calculation:
The calculation is complex and involves a multi-pole filter. A simplified representation of the core logic is:

`ITrend = (alpha - (alpha^2)/4) * price + 0.5 * (alpha^2) * price[1] - (alpha - 0.75 * (alpha^2)) * price[2] + 2 * (1 - alpha) * ITrend[1] - ((1 - alpha)^2) * ITrend[2]`

Where `price[1]` and `ITrend[1]` refer to the previous bar's values, `price[2]` and `ITrend[2]` are from two bars ago, and `alpha` is a smoothing constant derived from the lookback period.

---

## 4. Ehlers Roofing Filter

This indicator is designed to filter out high-frequency noise (whipsaws) from price data, leaving the smoother, more significant price movements.

### Concept:
It acts as a band-pass filter, allowing only frequencies within a specific range (e.g., cycles between 10 and 48 bars) to pass through. This effectively filters out market noise and very short-term volatility.

### Calculation:
The calculation involves applying a High-Pass filter to the data and then smoothing the result with a Super Smoother filter. The formulas are complex and rooted in digital signal processing.

---

## 5. Ehlers Center of Gravity (COG) Oscillator

This is a zero-lag oscillator designed to identify major turning points and swings in the market with minimal delay.

### Concept:
The COG oscillator calculates the "center of gravity" of prices over a given period. It provides a weighted average of prices, where more recent prices have a higher weight. This helps in identifying the balance point of price action. Crossovers between the COG line and its signal line (a moving average) are used to generate trade signals.

### Calculation:
The core formula is:
**`COG = - (Sum of (Price * Position)) / (Sum of Price)`**

Where:
- **`Price`** is the price for a specific bar.
- **`Position`** is the index of the bar (e.g., 1, 2, 3...).

#### Pseudocode:
```python
# period = 10
# numerator = 0
# denominator = 0

# for i from 0 to period - 1:
#   numerator += (1 + i) * price[i]
#   denominator += price[i]

# if denominator != 0:
#   cog = -numerator / denominator
# else:
#   cog = 0
```

---

## 6. Ehlers MESA Sine Wave

This indicator is used to identify if a market is in a trending or a cyclical mode. It consists of two lines: the Sine Wave and the Lead Sine Wave.

### Concept:
- When the Sine and Lead Sine waves cross, it indicates a potential reversal or turning point in the cycle.
- The distance between the two lines can indicate the strength of the trend.
- If the lines are clearly oscillating and crossing, the market is likely in a cycle mode.
- If the lines are flat or moving sideways, the market is likely in a trend mode.

### Calculation:
The calculation is complex and involves the Hilbert Transform to determine the phase and period of the dominant market cycle.

#### Pseudocode:
```python
# 1. Apply a high-pass filter to the price data to detrend it.
# hp = high_pass_filter(price)

# 2. Calculate the In-Phase (I) and Quadrature (Q) components using a Hilbert Transform.
# I, Q = hilbert_transform(hp)

# 3. Calculate the dominant cycle period.
# period = dominant_cycle_period(I, Q)

# 4. Calculate the phase angle.
# phase = arctan(Q / I)

# 5. Calculate the Sine Wave and Lead Sine Wave.
# sine_wave = sin(phase)
# lead_sine_wave = sin(phase + 45_degrees)
```

---

## 7. Ehlers Laguerre RSI

This is a more responsive version of the traditional RSI that uses a Laguerre filter to reduce lag and smooth the indicator.

### Concept:
- The Laguerre RSI is designed to react more quickly to price changes.
- It oscillates between 0 and 1.
- Values above 0.8 are considered overbought, and values below 0.2 are considered oversold.
- Crossovers of these levels can be used as trading signals.

### Calculation:
The calculation involves a smoothing factor `gamma` and a series of recursive equations.

#### Pseudocode:
```python
# gamma = 0.5 (typical)
# L0, L1, L2, L3 = 0, 0, 0, 0

# L0 = (1 - gamma) * price + gamma * L0_prev
# L1 = -gamma * L0 + L0_prev + gamma * L1_prev
# L2 = -gamma * L1 + L1_prev + gamma * L2_prev
# L3 = -gamma * L2 + L2_prev + gamma * L3_prev

# cu = 0
# cd = 0

# if L0 >= L1:
#   cu = L0 - L1
# else:
#   cd = L1 - L0

# if L1 >= L2:
#   cu += L1 - L2
# else:
#   cd += L2 - L1

# if L2 >= L3:
#   cu += L2 - L3
# else:
#   cd += L3 - L2

# if (cu + cd) != 0:
#   laguerre_rsi = cu / (cu + cd)
# else:
#   laguerre_rsi = 0
```

---

## 8. Ehlers Adaptive Cyber Cycle

This indicator is designed to adapt to changing market cycle periods, making it more responsive than static-period oscillators.

### Concept:
- The Adaptive Cyber Cycle oscillates around a zero line.
- Peaks and troughs in the indicator are intended to align with cyclical tops and bottoms in the price.
- Because it adapts its period, it can be more timely in signaling cycle turns.

### Calculation:
The calculation is a multi-step process that involves smoothing, calculating a basic cycle, and then making it adaptive.

#### Pseudocode:
```python
# 1. Smooth the price using a 4-bar symmetrical FIR filter.
# smoothed_price = (price + 2*price[1] + 2*price[2] + price[3]) / 6

# 2. Calculate the basic Cyber Cycle.
# alpha = 0.07
# cycle = (1 - 0.5*alpha)^2 * (smoothed_price - 2*smoothed_price[1] + smoothed_price[2]) + \
#         2*(1 - alpha)*cycle[1] - (1 - alpha)^2*cycle[2]

# 3. Determine the dominant cycle period (this is the complex part involving phase calculation).
# dominant_period = calculate_dominant_cycle(cycle)

# 4. Create the adaptive alpha and the final adaptive cycle.
# adaptive_alpha = 2 / (dominant_period + 1)
# adaptive_cycle = (1 - 0.5*adaptive_alpha)^2 * (smoothed_price - 2*smoothed_price[1] + smoothed_price[2]) + \
#                  2*(1 - adaptive_alpha)*adaptive_cycle[1] - (1 - adaptive_alpha)^2*adaptive_cycle[2]
```

---

## 9. Ehlers Correlation Trend Indicator (CTI)

The CTI measures the correlation between the price and an ideal upward trend line. It helps to identify the strength and direction of a trend.

### Concept:
- The indicator oscillates between -1 and 1.
- Values above 0.5 suggest a strong uptrend.
- Values below -0.5 suggest a strong downtrend.
- Values near 0 indicate a sideways or non-trending market.

### Calculation:
The calculation uses the Spearman correlation formula.

#### Pseudocode:
```python
# period = 20
# x = price data for the period
# y = an ideal trend line (e.g., a simple descending count from period-1 to 0)

# sx = sum of x
# sy = sum of y
# sxx = sum of x*x
# syy = sum of y*y
# sxy = sum of x*y

# numerator = period * sxy - sx * sy
# denominator = sqrt((period * sxx - sx^2) * (period * syy - sy^2))

# if denominator != 0:
#   cti = numerator / denominator
# else:
#   cti = 0
```

---

*Disclaimer: The formulas presented are simplified representations. For precise implementation, referring to John E-hlers' original papers or books is highly recommended.*
