# Helper functions for Technical Analysis
class TA:

    @staticmethod
    def safeArr(length, default_value=0):
        return [default_value] * length

    @staticmethod
    def sma(values, period):
        """Calculates the Simple Moving Average (SMA)."""
        if not values or len(values) < period:
            return TA.safeArr(len(values))

        sma_values = TA.safeArr(len(values))
        for i in range(period - 1, len(values)):
            window = values[i - period + 1 : i + 1]
            sma_values[i] = sum(window) / period
        return sma_values

    @staticmethod
    def ema(values, period):
        """Calculates the Exponential Moving Average (EMA)."""
        if not values or len(values) < period:
            return TA.safeArr(len(values))

        ema_values = TA.safeArr(len(values))
        multiplier = 2 / (period + 1)

        # Calculate initial SMA for the first EMA value
        sma = sum(values[0:period]) / period
        ema_values[period - 1] = sma

        # Calculate subsequent EMA values
        for i in range(period, len(values)):
            ema_values[i] = (values[i] - ema_values[i - 1]) * multiplier + ema_values[i - 1]
        return ema_values

    @staticmethod
    def atr(highs, lows, closes, period):
        """Calculates the Average True Range (ATR)."""
        if not highs or not lows or not closes or len(highs) < period:
            return TA.safeArr(len(highs))

        atr_values = TA.safeArr(len(highs))
        tr = TA.safeArr(len(highs))

        # Calculate True Range (TR) for each period
        tr[0] = 0 # TR is not defined for the first candle
        for i in range(1, len(highs)):
            highLow = highs[i] - lows[i]
            highClose = abs(highs[i] - closes[i - 1])
            lowClose = abs(lows[i] - closes[i - 1])
            tr[i] = max(highLow, highClose, lowClose)

        # Calculate initial ATR using SMA
        atr_values[period - 1] = sum(tr[1 : period]) / period

        # Calculate subsequent ATR values using EMA formula
        for i in range(period, len(highs)):
            atr_values[i] = (tr[i] - atr_values[i - 1]) * (1 / period) + atr_values[i - 1]

        return atr_values

    @staticmethod
    def r2(y_slice, y_predicted_linear):
        """Calculates the R-squared (coefficient of determination)."""
        if len(y_slice) != len(y_predicted_linear) or len(y_slice) < 2:
            return 0 # R-squared requires at least two data points

        mean_y = sum(y_slice) / len(y_slice)
        ss_res = 0 # Sum of squares of residuals
        ss_tot = 0 # Total sum of squares

        for i in range(len(y_slice)):
            ss_res += (y_slice[i] - y_predicted_linear[i]) ** 2
            ss_tot += (y_slice[i] - mean_y) ** 2

        if ss_tot == 0: return 1 # Avoid division by zero if all y values are the same

        r2 = 1 - (ss_res / ss_tot)
        # Check if r2 is NaN. NaN is the only value not equal to itself.
        return 0 if r2 != r2 else r2

    @staticmethod
    def bollinger(closes, period, stdDev):
        """Calculates the Bollinger Bands."""
        middle = TA.sma(closes, period)
        upper = TA.safeArr(len(closes))
        lower = TA.safeArr(len(closes))
        for i in range(period - 1, len(closes)):
            sumSqDiff = 0
            for j in range(period):
                sumSqDiff += (closes[i - j] - middle[i]) ** 2
            std = sumSqDiff ** 0.5 # Use ** 0.5 for square root
            upper[i] = middle[i] + stdDev * std
            lower[i] = middle[i] - stdDev * std
        return {"upper": upper, "middle": middle, "lower": lower}

    @staticmethod
    def keltner(highs, lows, closes, period, multiplier):
        """Calculates the Keltner Channels."""
        middle = TA.ema(closes, period)
        atr = TA.atr(highs, lows, closes, period)
        upper = []
        lower = []
        for i in range(len(closes)):
            upper_val = (middle[i] or 0) + (atr[i] or 0) * multiplier
            lower_val = (middle[i] or 0) - (atr[i] or 0) * multiplier
            upper.append(upper_val)
            lower.append(lower_val)
        return {"upper": upper, "middle": middle, "lower": lower}

    @staticmethod
    def superTrend(highs, lows, closes, period, factor):
        """Calculates the SuperTrend indicator."""
        atr = TA.atr(highs, lows, closes, period)
        trend = TA.safeArr(len(closes))
        value = TA.safeArr(len(closes))
        prevTrend = 1
        prevUpperBand = 0
        prevLowerBand = 0

        for i in range(len(closes)): # Use i for loop index
            midPoint = (highs[i] + lows[i]) / 2
            upperBand = midPoint + factor * (atr[i] or 0)
            lowerBand = midPoint - factor * (atr[i] or 0)

            if i == 0: # Use i for index comparison
                trend[i] = 1
                value[i] = lowerBand
                prevUpperBand = upperBand
                prevLowerBand = lowerBand
                continue

            currentTrend = trend[i - 1]
            if closes[i] > prevUpperBand:
                currentTrend = 1
            elif closes[i] < prevLowerBand:
                currentTrend = -1
            else:
                currentTrend = trend[i - 1]

            if currentTrend == 1:
                value[i] = max(lowerBand, prevLowerBand)
                prevUpperBand = upperBand
            else:
                value[i] = min(upperBand, prevUpperBand)
                prevLowerBand = lowerBand
            trend[i] = currentTrend
        return {"trend": trend, "value": value}

    @staticmethod
    def chandelierExit(highs, lows, closes, period, multiplier):
        """Calculates the Chandelier Exit indicator."""
        atr = TA.atr(highs, lows, closes, period)
        trend = TA.safeArr(len(closes))
        value = TA.safeArr(len(closes))
        prevTrend = 1

        for i in range(period - 1, len(closes)): # Use i for loop index
            highestHigh = max(highs[i - period + 1 : i + 1]) # Use slicing for subarray
            lowestLow = min(lows[i - period + 1 : i + 1]) # Use slicing for subarray
            currentATR = atr[i] or 0

            longStop = highestHigh - multiplier * currentATR
            shortStop = lowestLow + multiplier * currentATR

            if i == 0: # Use i for index comparison
                trend[i] = 1
                value[i] = longStop
                continue

            currentTrend = trend[i - 1]
            if closes[i] > value[i - 1] and currentTrend == -1:
                currentTrend = 1
            elif closes[i] < value[i - 1] and currentTrend == 1:
                currentTrend = -1

            if currentTrend == 1:
                value[i] = max(longStop, value[i - 1])
            else:
                value[i] = min(shortStop, value[i - 1])
            trend[i] = currentTrend
        return {"trend": trend, "value": value}

    @staticmethod
    def findFVG(candles):
        """Finds Fair Value Gaps (FVG)."""
        fvgs = []
        # Need at least 3 candles to detect a potential FVG
        if len(candles) < 3: return []

        for i in range(1, len(candles) - 1): # Use i for loop index
            prevCandle = candles[i - 1]
            currentCandle = candles[i]
            nextCandle = candles[i + 1]

            # Bullish FVG conditions
            is_bullish_pattern = (
                currentCandle["h"] > prevCandle["h"] and
                currentCandle["h"] > nextCandle["h"] and
                currentCandle["l"] < prevCandle["l"] and
                currentCandle["l"] < nextCandle["l"] and
                currentCandle["o"] < currentCandle["c"] and # Ensure middle candle is bullish
                nextCandle["h"] > currentCandle["l"] and
                nextCandle["l"] < currentCandle["h"]
            )

            # Bearish FVG conditions
            is_bearish_pattern = (
                currentCandle["l"] < prevCandle["l"] and
                currentCandle["l"] < nextCandle["l"] and
                currentCandle["h"] > prevCandle["h"] and
                currentCandle["h"] > nextCandle["h"] and
                currentCandle["o"] > currentCandle["c"] and # Ensure middle candle is bearish
                nextCandle["l"] < currentCandle["h"] and
                nextCandle["h"] > currentCandle["l"]
            )

            # Check for Bullish FVG
            if is_bullish_pattern:
                # Ensure there's a gap between the high of the current candle and the low of the next candle
                if currentCandle["h"] > nextCandle["l"]:
                    fvgs.append({
                        "price": (currentCandle["h"] + nextCandle["l"]) / 2, # Midpoint of the gap
                        "type": "BULLISH",
                        "top": currentCandle["h"], # Top of the FVG is the high of the current candle
                        "bottom": nextCandle["l"],  # Bottom of the FVG is the low of the next candle
                    })
            # Check for Bearish FVG
            elif is_bearish_pattern:
                # Ensure there's a gap between the low of the current candle and the high of the next candle
                if currentCandle["l"] < nextCandle["h"]:
                    fvgs.append({
                        "price": (currentCandle["l"] + nextCandle["h"]) / 2, # Midpoint of the gap
                        "type": "BEARISH",
                        "top": nextCandle["h"], # Top of the FVG is the high of the next candle
                        "bottom": currentCandle["l"],  # Bottom of the FVG is the low of the current candle
                    })

        # Return the most recent FVG if any exist, otherwise return an empty array
        return fvgs[-1] if fvgs else []

    @staticmethod
    def vwap(highs, lows, closes, volumes, period):
        """Calculates the Volume Weighted Average Price (VWAP)."""
        vwap = TA.safeArr(len(closes))
        cumulativeTPV = 0 # Cumulative Typical Price * Volume
        cumulativeV = 0 # Cumulative Volume

        for i in range(len(closes)): # Use i for loop index
            typicalPrice = (highs[i] + lows[i] + closes[i]) / 3
            tpv = typicalPrice * volumes[i]
            cumulativeTPV += tpv
            cumulativeV += volumes[i]

            # Calculate VWAP for the specified period
            if i >= period - 1:
                if cumulativeV > 0:
                    vwap[i] = cumulativeTPV / cumulativeV
                else:
                    vwap[i] = 0 # Avoid division by zero

                # Subtract the values of the oldest candle in the period for the next iteration
                if i - period + 1 >= 0:
                    oldestTypicalPrice = (highs[i - period + 1] + lows[i - period + 1] + closes[i - period + 1]) / 3
                    oldestTPV = oldestTypicalPrice * volumes[i - period + 1]
                    cumulativeTPV -= oldestTPV
                    cumulativeV -= volumes[i - period + 1]
        # Fill the initial part of the array with 0 or NaN if needed, as VWAP requires a full period
        for i in range(period - 1):
            vwap[i] = 0 # Or NaN, depending on desired behavior
        return vwap

    @staticmethod
    def cci(highs, lows, closes, period):
        """Calculates the Commodity Channel Index (CCI)."""
        tp = []
        for i in range(len(closes)): # Use i for loop index
            tp.append((highs[i] + lows[i] + closes[i]) / 3) # Typical Price

        smaTp = TA.sma(tp, period)
        cci = TA.safeArr(len(closes))

        for i in range(period - 1, len(tp)): # Use i for loop index
            meanDeviation = 0
            for j in range(period):
                meanDeviation += abs(tp[i - j] - smaTp[i])
            meanDeviation /= period

            divisor = 0.015 * meanDeviation
            if divisor == 0: # Use == for comparison
                cci[i] = 0 # Avoid division by zero
            else:
                cci[i] = (tp[i] - smaTp[i]) / divisor
        return cci
