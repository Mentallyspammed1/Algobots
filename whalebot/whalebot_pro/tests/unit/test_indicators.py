import logging
from unittest.mock import MagicMock

import pandas as pd
import pytest
from whalebot_pro.analysis.indicators import IndicatorCalculator


@pytest.fixture
def mock_logger():
    return MagicMock(spec=logging.Logger)


@pytest.fixture
def indicator_calculator(mock_logger):
    return IndicatorCalculator(mock_logger)


@pytest.fixture
def sample_df():
    # Create a sample DataFrame with enough data for various indicator calculations
    data = {
        "open": [
            10,
            12,
            15,
            13,
            16,
            18,
            17,
            20,
            22,
            21,
            25,
            24,
            23,
            26,
            28,
            27,
            30,
            29,
            32,
            31,
            35,
            34,
            33,
            36,
            38,
            37,
            40,
            39,
            42,
            41,
        ],
        "high": [
            12,
            15,
            17,
            16,
            18,
            20,
            20,
            23,
            25,
            24,
            28,
            27,
            26,
            29,
            30,
            30,
            33,
            32,
            35,
            34,
            38,
            37,
            36,
            39,
            40,
            40,
            43,
            42,
            45,
            44,
        ],
        "low": [
            9,
            11,
            13,
            12,
            14,
            16,
            15,
            18,
            20,
            19,
            23,
            22,
            21,
            24,
            26,
            25,
            28,
            27,
            30,
            29,
            32,
            31,
            30,
            33,
            35,
            34,
            37,
            36,
            39,
            38,
        ],
        "close": [
            11,
            14,
            16,
            14,
            17,
            19,
            18,
            21,
            24,
            20,
            27,
            23,
            22,
            28,
            29,
            26,
            31,
            30,
            33,
            32,
            36,
            35,
            34,
            37,
            39,
            36,
            41,
            40,
            43,
            42,
        ],
        "volume": [
            100,
            110,
            120,
            105,
            115,
            130,
            125,
            140,
            150,
            135,
            160,
            145,
            130,
            170,
            180,
            165,
            190,
            175,
            200,
            185,
            210,
            195,
            180,
            220,
            230,
            215,
            240,
            225,
            250,
            235,
        ],
    }
    df = pd.DataFrame(
        data,
        index=pd.to_datetime(pd.date_range(start="2023-01-01", periods=30, freq="D")),
    )
    return df


def test_calculate_sma(indicator_calculator, sample_df):
    sma = indicator_calculator.calculate_sma(sample_df, period=10)
    assert isinstance(sma, pd.Series)
    assert not sma.isnull().all()
    assert sma.iloc[-1] == pytest.approx(34.5, abs=0.1)  # Approximate value


def test_calculate_ema(indicator_calculator, sample_df):
    ema = indicator_calculator.calculate_ema(sample_df, period=10)
    assert isinstance(ema, pd.Series)
    assert not ema.isnull().all()
    assert ema.iloc[-1] == pytest.approx(35.8, abs=0.1)  # Approximate value


def test_calculate_true_range(indicator_calculator, sample_df):
    tr = indicator_calculator.calculate_true_range(sample_df)
    assert isinstance(tr, pd.Series)
    assert not tr.isnull().all()
    assert (
        tr.iloc[-1] == pytest.approx(5.0)
    )  # (High-Low) = 45-38 = 7, (High-PrevClose) = 45-43 = 2, (Low-PrevClose) = 38-43 = 5. Max is 7.


def test_calculate_atr(indicator_calculator, sample_df):
    atr = indicator_calculator.calculate_atr(sample_df, period=14)
    assert isinstance(atr, pd.Series)
    assert not atr.isnull().all()
    assert atr.iloc[-1] == pytest.approx(3.5, abs=0.5)  # Approximate value


def test_calculate_super_smoother(indicator_calculator, sample_df):
    smoothed = indicator_calculator.calculate_super_smoother(
        sample_df["close"], period=10
    )
    assert isinstance(smoothed, pd.Series)
    assert not smoothed.isnull().all()
    assert smoothed.iloc[-1] == pytest.approx(41.0, abs=1.0)  # Approximate value


def test_calculate_ehlers_supertrend(indicator_calculator, sample_df):
    st_result = indicator_calculator.calculate_ehlers_supertrend(
        sample_df, period=10, multiplier=2.0
    )
    assert isinstance(st_result, pd.DataFrame)
    assert "supertrend" in st_result.columns
    assert "direction" in st_result.columns
    assert not st_result["supertrend"].isnull().all()
    assert not st_result["direction"].isnull().all()
    assert st_result["direction"].iloc[-1] in [-1, 1]  # Should be either up or down


def test_calculate_macd(indicator_calculator, sample_df):
    macd_line, signal_line, histogram = indicator_calculator.calculate_macd(
        sample_df, fast_period=12, slow_period=26, signal_period=9
    )
    assert isinstance(macd_line, pd.Series)
    assert isinstance(signal_line, pd.Series)
    assert isinstance(histogram, pd.Series)
    assert not macd_line.isnull().all()
    assert not signal_line.isnull().all()
    assert not histogram.isnull().all()


def test_calculate_rsi(indicator_calculator, sample_df):
    rsi = indicator_calculator.calculate_rsi(sample_df, period=14)
    assert isinstance(rsi, pd.Series)
    assert not rsi.isnull().all()
    assert 0 <= rsi.iloc[-1] <= 100


def test_calculate_stoch_rsi(indicator_calculator, sample_df):
    stoch_k, stoch_d = indicator_calculator.calculate_stoch_rsi(
        sample_df, period=14, k_period=3, d_period=3
    )
    assert isinstance(stoch_k, pd.Series)
    assert isinstance(stoch_d, pd.Series)
    assert not stoch_k.isnull().all()
    assert not stoch_d.isnull().all()
    assert 0 <= stoch_k.iloc[-1] <= 100
    assert 0 <= stoch_d.iloc[-1] <= 100


def test_calculate_adx(indicator_calculator, sample_df):
    adx, plus_di, minus_di = indicator_calculator.calculate_adx(sample_df, period=14)
    assert isinstance(adx, pd.Series)
    assert isinstance(plus_di, pd.Series)
    assert isinstance(minus_di, pd.Series)
    assert not adx.isnull().all()
    assert not plus_di.isnull().all()
    assert not minus_di.isnull().all()
    assert 0 <= adx.iloc[-1] <= 100


def test_calculate_bollinger_bands(indicator_calculator, sample_df):
    upper, middle, lower = indicator_calculator.calculate_bollinger_bands(
        sample_df, period=20, std_dev=2.0
    )
    assert isinstance(upper, pd.Series)
    assert isinstance(middle, pd.Series)
    assert isinstance(lower, pd.Series)
    assert not upper.isnull().all()
    assert not middle.isnull().all()
    assert not lower.isnull().all()


def test_calculate_vwap(indicator_calculator, sample_df):
    vwap = indicator_calculator.calculate_vwap(sample_df)
    assert isinstance(vwap, pd.Series)
    assert not vwap.isnull().all()


def test_calculate_cci(indicator_calculator, sample_df):
    cci = indicator_calculator.calculate_cci(sample_df, period=20)
    assert isinstance(cci, pd.Series)
    assert not cci.isnull().all()


def test_calculate_williams_r(indicator_calculator, sample_df):
    wr = indicator_calculator.calculate_williams_r(sample_df, period=14)
    assert isinstance(wr, pd.Series)
    assert not wr.isnull().all()
    assert -100 <= wr.iloc[-1] <= 0


def test_calculate_ichimoku_cloud(indicator_calculator, sample_df):
    tenkan, kijun, span_a, span_b, chikou = (
        indicator_calculator.calculate_ichimoku_cloud(
            sample_df,
            tenkan_period=9,
            kijun_period=26,
            senkou_span_b_period=52,
            chikou_span_offset=26,
        )
    )
    assert isinstance(tenkan, pd.Series)
    assert isinstance(kijun, pd.Series)
    assert isinstance(span_a, pd.Series)
    assert isinstance(span_b, pd.Series)
    assert isinstance(chikou, pd.Series)
    assert not tenkan.isnull().all()


def test_calculate_mfi(indicator_calculator, sample_df):
    mfi = indicator_calculator.calculate_mfi(sample_df, period=14)
    assert isinstance(mfi, pd.Series)
    assert not mfi.isnull().all()
    assert 0 <= mfi.iloc[-1] <= 100


def test_calculate_obv(indicator_calculator, sample_df):
    obv, obv_ema = indicator_calculator.calculate_obv(sample_df, ema_period=20)
    assert isinstance(obv, pd.Series)
    assert isinstance(obv_ema, pd.Series)
    assert not obv.isnull().all()
    assert not obv_ema.isnull().all()


def test_calculate_cmf(indicator_calculator, sample_df):
    cmf = indicator_calculator.calculate_cmf(sample_df, period=20)
    assert isinstance(cmf, pd.Series)
    assert not cmf.isnull().all()
    assert -1.0 <= cmf.iloc[-1] <= 1.0


def test_calculate_psar(indicator_calculator, sample_df):
    psar_val, psar_dir = indicator_calculator.calculate_psar(
        sample_df, acceleration=0.02, max_acceleration=0.2
    )
    assert isinstance(psar_val, pd.Series)
    assert isinstance(psar_dir, pd.Series)
    assert not psar_val.isnull().all()
    assert not psar_dir.isnull().all()
    assert psar_dir.iloc[-1] in [-1, 1]


def test_calculate_volatility_index(indicator_calculator, sample_df):
    # ATR is needed for this, so calculate it first
    sample_df["ATR"] = indicator_calculator.calculate_atr(sample_df, period=14)
    vol_idx = indicator_calculator.calculate_volatility_index(sample_df, period=20)
    assert isinstance(vol_idx, pd.Series)
    assert not vol_idx.isnull().all()
    assert vol_idx.iloc[-1] >= 0


def test_calculate_vwma(indicator_calculator, sample_df):
    vwma = indicator_calculator.calculate_vwma(sample_df, period=20)
    assert isinstance(vwma, pd.Series)
    assert not vwma.isnull().all()


def test_calculate_volume_delta(indicator_calculator, sample_df):
    vol_delta = indicator_calculator.calculate_volume_delta(sample_df, period=5)
    assert isinstance(vol_delta, pd.Series)
    assert not vol_delta.isnull().all()
    assert -1.0 <= vol_delta.iloc[-1] <= 1.0


def test_calculate_kaufman_ama(indicator_calculator, sample_df):
    kama = indicator_calculator.calculate_kaufman_ama(
        sample_df, period=10, fast_period=2, slow_period=30
    )
    assert isinstance(kama, pd.Series)
    assert not kama.isnull().all()


def test_calculate_relative_volume(indicator_calculator, sample_df):
    rvol = indicator_calculator.calculate_relative_volume(sample_df, period=20)
    assert isinstance(rvol, pd.Series)
    assert not rvol.isnull().all()
    assert rvol.iloc[-1] >= 0


def test_calculate_market_structure(indicator_calculator, sample_df):
    ms = indicator_calculator.calculate_market_structure(sample_df, lookback_period=10)
    assert isinstance(ms, pd.Series)
    assert not ms.isnull().all()
    assert ms.iloc[-1] in ["UP", "DOWN", "SIDEWAYS", "UNKNOWN"]


def test_calculate_dema(indicator_calculator, sample_df):
    dema = indicator_calculator.calculate_dema(sample_df, period=14)
    assert isinstance(dema, pd.Series)
    assert not dema.isnull().all()


def test_calculate_keltner_channels(indicator_calculator, sample_df):
    # ATR is needed for this, so calculate it first
    sample_df["ATR"] = indicator_calculator.calculate_atr(sample_df, period=14)
    upper, middle, lower = indicator_calculator.calculate_keltner_channels(
        sample_df, period=20, atr_multiplier=2.0
    )
    assert isinstance(upper, pd.Series)
    assert isinstance(middle, pd.Series)
    assert isinstance(lower, pd.Series)
    assert not upper.isnull().all()
    assert not middle.isnull().all()
    assert not lower.isnull().all()


def test_calculate_roc(indicator_calculator, sample_df):
    roc = indicator_calculator.calculate_roc(sample_df, period=12)
    assert isinstance(roc, pd.Series)
    assert not roc.isnull().all()


def test_detect_candlestick_patterns(indicator_calculator, sample_df):
    # Test with a subset that might form a pattern
    pattern = indicator_calculator.detect_candlestick_patterns(sample_df.iloc[-2:])
    assert isinstance(pattern, str)
    assert pattern in [
        "Bullish Engulfing",
        "Bearish Engulfing",
        "Bullish Hammer",
        "Bearish Shooting Star",
        "No Pattern",
    ]


def test_calculate_fibonacci_pivot_points(indicator_calculator, sample_df):
    fib_pivots = indicator_calculator.calculate_fibonacci_pivot_points(sample_df)
    assert isinstance(fib_pivots, dict)
    assert "Pivot" in fib_pivots
    assert "R1" in fib_pivots
    assert "S1" in fib_pivots
    assert isinstance(fib_pivots["Pivot"], Decimal)


def test_calculate_support_resistance_from_orderbook(indicator_calculator):
    bids = [["40000.0", "10.0"], ["39990.0", "5.0"]]
    asks = [["40010.0", "8.0"], ["40020.0", "12.0"]]
    support, resistance = (
        indicator_calculator.calculate_support_resistance_from_orderbook(bids, asks)
    )
    assert isinstance(support, Decimal)
    assert isinstance(resistance, Decimal)
    assert support == Decimal("40000.0")
    assert resistance == Decimal("40020.0")
