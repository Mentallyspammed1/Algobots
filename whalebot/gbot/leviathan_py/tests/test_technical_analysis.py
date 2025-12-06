"""
Tests for the vectorized Technical Analysis functions.
"""
import numpy as np
import pytest
from src import technical_analysis as ta

@pytest.fixture
def sample_kline_data():
    """Provides a sample of kline data for testing."""
    # Using a larger, more realistic dataset
    closes = np.array([
        100, 102, 105, 103, 104, 106, 108, 110, 109, 107,
        112, 115, 113, 114, 116, 118, 120, 119, 117, 122
    ], dtype=float)
    highs = closes + 2
    lows = closes - 2
    volumes = np.random.randint(100, 1000, size=len(closes)).astype(float)
    return {'high': highs, 'low': lows, 'close': closes, 'volume': volumes}

def test_sma(sample_kline_data):
    closes = sample_kline_data['close']
    period = 5
    sma_vals = ta.sma(closes, period)
    
    assert sma_vals.shape == closes.shape
    assert np.isnan(sma_vals[:period-1]).all()
    # Manual calculation for the first valid SMA
    expected_first_sma = np.mean(closes[:5])
    assert np.isclose(sma_vals[4], expected_first_sma)
    # Manual calculation for the last valid SMA
    expected_last_sma = np.mean(closes[-5:])
    assert np.isclose(sma_vals[-1], expected_last_sma)

def test_sma_edge_cases():
    assert ta.sma(np.array([]), 5).size == 0
    short_array = np.array([1, 2, 3])
    assert np.isnan(ta.sma(short_array, 5)).all()

def test_atr(sample_kline_data):
    highs, lows, closes = sample_kline_data['high'], sample_kline_data['low'], sample_kline_data['close']
    period = 14
    atr_vals = ta.atr(highs, lows, closes, period)
    
    assert atr_vals.shape == closes.shape
    assert atr_vals.size > 0
    # ATR calculation is complex, so we check for reasonable values, not exact.
    assert not np.isnan(atr_vals[-1])
    assert atr_vals[-1] > 0

def test_vwap(sample_kline_data):
    highs, lows, closes, volumes = sample_kline_data['high'], sample_kline_data['low'], sample_kline_data['close'], sample_kline_data['volume']
    
    # Test with full lookback
    vwap_val = ta.vwap(highs, lows, closes, volumes, lookback=len(closes))
    assert vwap_val is not None
    
    # Manual calculation for a small slice
    lookback = 5
    h_slice, l_slice, c_slice, v_slice = highs[-lookback:], lows[-lookback:], closes[-lookback:], volumes[-lookback:]
    tp = (h_slice + l_slice + c_slice) / 3
    expected_vwap = np.sum(tp * v_slice) / np.sum(v_slice)
    
    vwap_slice = ta.vwap(h_slice, l_slice, c_slice, v_slice, lookback=lookback)
    assert np.isclose(vwap_slice, expected_vwap)

def test_fisher(sample_kline_data):
    highs, lows = sample_kline_data['high'], sample_kline_data['low']
    period = 9
    fisher_vals = ta.fisher(highs, lows, period)
    
    assert fisher_vals.shape == highs.shape
    assert np.isnan(fisher_vals[:period-1]).all()
    assert not np.isnan(fisher_vals[period:]).any()
    
    # Fisher transform values should typically be within a certain range, e.g., -5 to 5
    # This is not a strict rule but a good sanity check
    assert np.all(fisher_vals[period-1:] > -10)
    assert np.all(fisher_vals[period-1:] < 10)

def test_fisher_flat_input():
    size = 20
    highs = np.full(size, 100)
    lows = np.full(size, 100)
    period = 9
    fisher_vals = ta.fisher(highs, lows, period)
    # With flat input, the range is zero, and the value should not explode
    assert not np.isinf(fisher_vals).any()
    assert not np.isnan(fisher_vals[period:]).any()
    # Should result in values close to zero after smoothing
    assert np.isclose(fisher_vals[-1], 0, atol=1e-5)
