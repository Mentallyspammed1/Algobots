import pandas as pd
import numpy as np
from indicators import EhlersIndicators, MomentumIndicators, VolatilityIndicators, calculate_supertrend

def test_indicators():
    print("Testing Indicators...")
    
    # Create dummy data
    np.random.seed(42)
    data = {
        'high': np.random.uniform(100, 110, 100),
        'low': np.random.uniform(90, 100, 100),
        'close': np.random.uniform(95, 105, 100),
        'volume': np.random.uniform(1000, 5000, 100)
    }
    df = pd.DataFrame(data)
    close = df['close']

    # Test SuperSmoother
    ss = EhlersIndicators.super_smoother(close, 10)
    print(f"SuperSmoother: {ss.iloc[-1]:.4f}")

    # Test Fisher
    fisher, signal = EhlersIndicators.fisher_transform(close, 10)
    print(f"Fisher: {fisher.iloc[-1]:.4f}, Signal: {signal.iloc[-1]:.4f}")

    # Test Laguerre RSI
    lrsi = EhlersIndicators.laguerre_rsi(close, 0.5)
    print(f"Laguerre RSI: {lrsi.iloc[-1]:.4f}")

    # Test CTI
    cti = EhlersIndicators.correlation_trend_indicator(close, 20)
    print(f"CTI: {cti.iloc[-1]:.4f}")

    # Test SuperTrend
    st = calculate_supertrend(df)
    print(f"SuperTrend: {st['supertrend'].iloc[-1]:.4f}, Direction: {st['direction'].iloc[-1]}")

    # Test Roofing Filter
    roof = EhlersIndicators.roofing_filter(close, 10, 48)
    print(f"Roofing Filter: {roof.iloc[-1]:.4f}")

    # Test Ehlers Stoch RSI
    esk, esd = EhlersIndicators.ehlers_stoch_rsi(close, 14)
    print(f"Ehlers Stoch RSI K: {esk.iloc[-1]:.4f}, D: {esd.iloc[-1]:.4f}")

    # Test Cyber Cycle
    cyc, cys = EhlersIndicators.cyber_cycle(close, 0.07)
    print(f"Cyber Cycle: {cyc.iloc[-1]:.4f}, Signal: {cys.iloc[-1]:.4f}")

    # Test MESA Sine Wave
    ms, mls = EhlersIndicators.mesa_sine_wave(close)
    print(f"MESA Sine: {ms.iloc[-1]:.4f}, LeadSine: {mls.iloc[-1]:.4f}")

    # Test MACD
    m, msig, mh = MomentumIndicators.macd(close)
    print(f"MACD Hist: {mh.iloc[-1]:.4f}")

    # Test ADX
    adx = MomentumIndicators.adx(df['high'], df['low'], close, 14)
    print(f"ADX: {adx.iloc[-1]:.4f}")

    # Test FVE
    fve = MomentumIndicators.fve(close, df['volume'], 22)
    print(f"FVE: {fve.iloc[-1]:.4f}")

    # Test HMA, WMA, VWAP
    hma_v = MomentumIndicators.hma(close, 20)
    wma_v = MomentumIndicators.wma(close, 20)
    vwap_v = MomentumIndicators.vwap(df)
    print(f"HMA(20): {hma_v.iloc[-1]:.4f}")
    print(f"WMA(20): {wma_v.iloc[-1]:.4f}")
    print(f"VWAP: {vwap_v.iloc[-1]:.4f}")

    print("Indicator tests passed!")

if __name__ == "__main__":
    test_indicators()
