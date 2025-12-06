"""
Tests for the OracleBrain class.
"""
import pytest
import os
from unittest.mock import MagicMock, AsyncMock, patch
import numpy as np
from src.oracle import OracleBrain

# Mock kline data for building context
@pytest.fixture
def sample_kline_context_data():
    klines = [{'high': 100+i, 'low': 98+i, 'close': 99+i, 'volume': 1000+i*10} for i in range(101)]
    mtf_klines = [{'high': 199+i, 'low': 198+i, 'close': 199+i, 'volume': 100} for i in range(21)]
    return klines, mtf_klines

# Mock order book metrics
@pytest.fixture
def sample_book_metrics():
    return {'skew': 0.25, 'wall_status': 'BID_SUPPORT'}

# Mock successful AI response
@pytest.fixture
def mock_gemini_model_success():
    mock_response = MagicMock()
    # The response from generate_content_async has a 'text' attribute
    mock_response.text = '{"action": "BUY", "confidence": 0.95, "sl": 98.0, "tp": 105.0, "reason": "Strong bullish signal"}'
    
    # The model's generate_content_async method is what we need to mock
    model_mock = MagicMock()
    model_mock.generate_content_async = AsyncMock(return_value=mock_response)
    return model_mock

# Mock failed AI response (e.g., malformed JSON)
@pytest.fixture
def mock_gemini_model_fail():
    mock_response = MagicMock()
    mock_response.text = '{"action": "BUY", "confiden' # Malformed
    
    model_mock = MagicMock()
    model_mock.generate_content_async = AsyncMock(return_value=mock_response)
    return model_mock

# Set dummy API key for tests
@pytest.fixture(autouse=True)
def set_env_vars():
    os.environ['GEMINI_API_KEY'] = 'test_key'

def test_oracle_brain_init():
    """Test that the OracleBrain initializes correctly."""
    with patch('google.generativeai.GenerativeModel') as _:
         brain = OracleBrain()
    assert brain is not None
    with pytest.raises(ValueError):
        with patch.dict(os.environ, {'GEMINI_API_KEY': ''}):
            OracleBrain()

def test_build_context(sample_kline_context_data, sample_book_metrics):
    """Test the context building logic."""
    klines, mtf_klines = sample_kline_context_data
    brain = OracleBrain()
    brain.klines = klines
    brain.mtf_klines = mtf_klines
    
    context = brain.build_context(sample_book_metrics)
    
    assert context is not None
    assert 'price' in context
    assert 'atr' in context
    assert 'vwap' in context
    assert 'fisher' in context
    assert 'fastTrend' in context
    assert 'book' in context
    assert context['fastTrend'] == 'BULLISH' # last mtf_kline > sma20
    assert context['book']['skew'] == 0.25

def test_build_context_insufficient_data(sample_book_metrics):
    """Test context building with not enough data."""
    brain = OracleBrain()
    brain.klines = [{'high': 1, 'low': 1, 'close': 1, 'volume': 1}] * 50 # Less than 100
    context = brain.build_context(sample_book_metrics)
    assert context is None

@pytest.mark.asyncio
async def test_divine_success(sample_kline_context_data, sample_book_metrics, mock_gemini_model_success):
    """Test a successful AI signal generation."""
    with patch('google.generativeai.GenerativeModel', return_value=mock_gemini_model_success):
        brain = OracleBrain()
    
    klines, mtf_klines = sample_kline_context_data
    brain.klines = klines
    brain.mtf_klines = mtf_klines

    signal = await brain.divine(sample_book_metrics)
    
    assert signal['action'] == 'BUY'
    assert signal['confidence'] == 0.95
    assert signal['sl'] == 98.0
    assert 'R/R Enforced' in signal['reason'] # Test R/R enforcement

@pytest.mark.asyncio
async def test_divine_failure(sample_kline_context_data, sample_book_metrics, mock_gemini_model_fail):
    """Test a failed AI signal generation (e.g., parsing error)."""
    with patch('google.generativeai.GenerativeModel', return_value=mock_gemini_model_fail):
        brain = OracleBrain()

    klines, mtf_klines = sample_kline_context_data
    brain.klines = klines
    brain.mtf_klines = mtf_klines

    signal = await brain.divine(sample_book_metrics)
    
    assert signal['action'] == 'HOLD'
    assert signal['confidence'] == 0
    assert 'Oracle Error' in signal['reason']

def test_validate_signal():
    """Test the signal validation and sanitization logic."""
    brain = OracleBrain()
    context = {'price': 100, 'atr': 5}
    
    # Valid signal
    good_signal = {'action': 'BUY', 'confidence': 0.9, 'sl': 95, 'tp': 110}
    validated = brain._validate_signal(good_signal, context)
    assert validated['action'] == 'BUY'
    
    # Low confidence
    low_conf_signal = {'action': 'BUY', 'confidence': 0.8, 'sl': 95, 'tp': 110}
    validated = brain._validate_signal(low_conf_signal, context)
    assert validated['action'] == 'HOLD'

    # Invalid action
    bad_action_signal = {'action': 'PUMP', 'confidence': 0.95}
    validated = brain._validate_signal(bad_action_signal, context)
    assert validated['action'] == 'HOLD'

    # SL/TP clipping
    extreme_sl_tp_signal = {'action': 'BUY', 'confidence': 0.95, 'sl': 50, 'tp': 150}
    validated = brain._validate_signal(extreme_sl_tp_signal, context)
    assert validated['sl'] == 80.0 # 100 - (5 * 4)
    assert validated['tp'] == 120.0 # 100 + (5 * 4)
