
import { 
  RSI, MACD, BollingerBands, ADX, ATR, OBV, SMA
} from 'technicalindicators';
import { Kline, IndicatorData, TrendDirection } from '../types';

/**
 * Calculates a comprehensive set of technical indicators from market data.
 * This function mirrors the functionality of the Python technical_analysis.py module.
 * 
 * @param klines - An array of Kline data, sorted chronologically.
 * @returns An IndicatorData object populated with the latest indicator values.
 */
export const calculateAllIndicators = (klines: Kline[]): IndicatorData => {
  if (klines.length < 26) {
    console.warn("Not enough data to calculate all indicators. At least 26 periods are recommended.");
    return {};
  }

  // Prepare input arrays for the technicalindicators library
  const highs = klines.map(k => k.high);
  const lows = klines.map(k => k.low);
  const closes = klines.map(k => k.close);
  const volumes = klines.map(k => k.volume);

  try {
    // Momentum
    const rsiResult = RSI.calculate({ period: 14, values: closes });
    const macdResult = MACD.calculate({
      values: closes,
      fastPeriod: 12,
      slowPeriod: 26,
      signalPeriod: 9,
      SimpleMAOscillator: false,
      SimpleMASignal: false
    });

    // Trend
    const adxResult = ADX.calculate({
        high: highs,
        low: lows,
        close: closes,
        period: 14
    });

    // Volatility
    const atrResult = ATR.calculate({ high: highs, low: lows, close: closes, period: 14 });
    const bbResult = BollingerBands.calculate({ period: 20, values: closes, stdDev: 2 });
    
    // Volume
    const obvResult = OBV.calculate({ close: closes, volume: volumes });

    // Manual VWAP Calculation for the entire period
    let cumulativeTypicalPriceVolume = 0;
    let cumulativeVolume = 0;
    for (const kline of klines) {
        const typicalPrice = (kline.high + kline.low + kline.close) / 3;
        cumulativeTypicalPriceVolume += typicalPrice * kline.volume;
        cumulativeVolume += kline.volume;
    }
    const vwap = cumulativeVolume > 0 ? cumulativeTypicalPriceVolume / cumulativeVolume : undefined;

    // Assemble the final data object, taking the last value from each calculation
    const indicatorData: IndicatorData = {
      momentum: {
        rsi: rsiResult[rsiResult.length - 1],
        macd: macdResult[macdResult.length - 1]?.MACD,
        macd_signal: macdResult[macdResult.length - 1]?.signal,
        macd_histogram: macdResult[macdResult.length - 1]?.histogram,
      },
      trend: {
        adx: adxResult[adxResult.length-1]?.adx,
        plus_di: adxResult[adxResult.length-1]?.pdi,
        minus_di: adxResult[adxResult.length-1]?.mdi,
      },
      volatility: {
        atr: atrResult[atrResult.length - 1],
        bb_upper: bbResult[bbResult.length - 1]?.upper,
        bb_middle: bbResult[bbResult.length - 1]?.middle,
        bb_lower: bbResult[bbResult.length - 1]?.lower,
        bb_width: bbResult[bbResult.length - 1] 
            ? (bbResult[bbResult.length - 1].upper - bbResult[bbResult.length - 1].lower) / bbResult[bbResult.length - 1].middle
            : undefined,
      },
      volume: {
        obv: obvResult[obvResult.length - 1],
        vwap: vwap
      }
    };
    
    return indicatorData;

  } catch (error) {
    console.error("An error occurred during indicator calculation:", error);
    return {};
  }
};


/**
 * Determines the general trend of a given kline series using a 50-period SMA.
 * @param klines - An array of Kline data.
 * @returns The determined trend direction ('Uptrend', 'Downtrend', 'Sideways').
 */
export const determineTrendFromKlines = (klines: Kline[]): TrendDirection => {
    const smaPeriod = 50;
    if (klines.length < smaPeriod) {
        return 'Sideways';
    }
    
    const closes = klines.map(k => k.close);
    const sma50Result = SMA.calculate({ period: smaPeriod, values: closes });
    const lastSma = sma50Result[sma50Result.length - 1];
    const lastClose = closes[closes.length - 1];

    if (!lastSma) {
        return 'Sideways';
    }

    if (lastClose > lastSma) {
        return 'Uptrend';
    } else if (lastClose < lastSma) {
        return 'Downtrend';
    } else {
        return 'Sideways';
    }
};
