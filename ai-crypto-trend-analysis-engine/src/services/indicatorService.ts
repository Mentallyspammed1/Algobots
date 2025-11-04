
import { 
  RSI, MACD, BollingerBands, ADX, ATR, OBV, SMA, Stochastic, WilliamsR, IchimokuCloud, StochasticRSI, FisherTransform
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
  if (klines.length < 52) { // Ichimoku requires a longer period
    console.warn("Not enough data to calculate all indicators. At least 52 periods are recommended for Ichimoku Cloud.");
    return {};
  }

  // Prepare input arrays for the technicalindicators library
  const highs = klines.map(k => k.high);
  const lows = klines.map(k => k.low);
  const closes = klines.map(k => k.close);
  const volumes = klines.map(k => k.volume);
  const ichimokuInput = { high: highs, low: lows, conversionPeriod: 9, basePeriod: 26, spanPeriod: 52, displacement: 26 };
  const stochasticInput = { high: highs, low: lows, close: closes, period: 14, signalPeriod: 3 };

  try {
    // Momentum
    const rsiResult = RSI.calculate({ period: 14, values: closes });
    const macdResult = MACD.calculate({ values: closes, fastPeriod: 12, slowPeriod: 26, signalPeriod: 9, SimpleMAOscillator: false, SimpleMASignal: false });
    const stochResult = Stochastic.calculate(stochasticInput);
    const williamsRResult = WilliamsR.calculate({ high: highs, low: lows, close: closes, period: 14 });

    // Trend
    const adxResult = ADX.calculate({ high: highs, low: lows, close: closes, period: 14 });
    const ichimokuResult = IchimokuCloud.calculate(ichimokuInput);

    // Volatility
    const atrResult = ATR.calculate({ high: highs, low: lows, close: closes, period: 14 });
    const bbResult = BollingerBands.calculate({ period: 20, values: closes, stdDev: 2 });
    
    // Volume
    const obvResult = OBV.calculate({ close: closes, volume: volumes });

    // Ehlers / Advanced
    const stochRsiResult = StochasticRSI.calculate({ rsiPeriod: 14, stochasticPeriod: 14, kPeriod: 3, dPeriod: 3, values: closes });
    const fisherResult = FisherTransform.calculate({ high: highs, low: lows, period: 9 });

    // Calculate a 20-period rolling VWAP for more responsive, short-term analysis.
    const vwapPeriod = 20;
    const recentKlines = klines.slice(-vwapPeriod);
    let cumulativeTypicalPriceVolume = 0;
    let cumulativeVolume = 0;
    for (const kline of recentKlines) {
        const typicalPrice = (kline.high + kline.low + kline.close) / 3;
        cumulativeTypicalPriceVolume += typicalPrice * kline.volume;
        cumulativeVolume += kline.volume;
    }
    const vwap = cumulativeVolume > 0 ? cumulativeTypicalPriceVolume / cumulativeVolume : undefined;

    // Assemble the final data object, taking the last value from each calculation
    const indicatorData: IndicatorData = {
      momentum: {
        rsi: rsiResult.slice(-1)[0],
        macd: macdResult.slice(-1)[0]?.MACD,
        macd_signal: macdResult.slice(-1)[0]?.signal,
        macd_histogram: macdResult.slice(-1)[0]?.histogram,
        stochastic_k: stochResult.slice(-1)[0]?.k,
        stochastic_d: stochResult.slice(-1)[0]?.d,
        williamsr: williamsRResult.slice(-1)[0],
      },
      trend: {
        adx: adxResult.slice(-1)[0]?.adx,
        plus_di: adxResult.slice(-1)[0]?.pdi,
        minus_di: adxResult.slice(-1)[0]?.mdi,
        ichimoku_conversion: ichimokuResult.slice(-1)[0]?.conversion,
        ichimoku_base: ichimokuResult.slice(-1)[0]?.base,
        ichimoku_span_a: ichimokuResult.slice(-1)[0]?.spanA,
        ichimoku_span_b: ichimokuResult.slice(-1)[0]?.spanB,
        ichimoku_lagging: closes.slice(-26)[0], // Lagging span is current close plotted 26 periods in the past.
      },
      volatility: {
        atr: atrResult.slice(-1)[0],
        bb_upper: bbResult.slice(-1)[0]?.upper,
        bb_middle: bbResult.slice(-1)[0]?.middle,
        bb_lower: bbResult.slice(-1)[0]?.lower,
        bb_width: bbResult.slice(-1)[0] 
            ? (bbResult.slice(-1)[0].upper - bbResult.slice(-1)[0].lower) / bbResult.slice(-1)[0].middle
            : undefined,
      },
      volume: {
        obv: obvResult.slice(-1)[0],
        vwap: vwap
      },
      ehlers: {
          stoch_rsi_k: stochRsiResult.slice(-1)[0]?.k,
          stoch_rsi_d: stochRsiResult.slice(-1)[0]?.d,
          fisher_transform: fisherResult.slice(-1)[0]?.fisher,
          fisher_trigger: fisherResult.slice(-1)[0]?.trigger,
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