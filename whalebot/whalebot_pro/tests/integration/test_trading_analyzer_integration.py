
import pytest
import asyncio
import logging
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
import numpy as np

from whalebot_pro.analysis.trading_analyzer import TradingAnalyzer
from whalebot_pro.analysis.indicators import IndicatorCalculator
from whalebot_pro.orderbook.advanced_orderbook_manager import AdvancedOrderbookManager, PriceLevel
from whalebot_pro.config import Config

@pytest.fixture
def mock_logger():
    return MagicMock(spec=logging.Logger)

@pytest.fixture
def mock_config():
    cfg = MagicMock(spec=Config)
    cfg.symbol = "BTCUSDT"
    cfg.get_config.return_value = {
        "symbol": "BTCUSDT",
        "interval": "15m",
        "orderbook_limit": 50,
        "signal_score_threshold": 2.0,
        "cooldown_sec": 60,
        "hysteresis_ratio": 0.85,
        "mtf_analysis": {"enabled": False},
        "ml_enhancement": {"sentiment_analysis_enabled": False},
        "indicators": {
            "ema_alignment": True, "sma_trend_filter": True, "momentum": True,
            "bollinger_bands": True, "vwap": True, "psar": True,
            "orderbook_imbalance": True, "fibonacci_levels": True,
            "ehlers_supertrend": True, "macd": True, "adx": True,
            "ichimoku_cloud": True, "obv": True, "cmf": True,
            "volatility_index": True, "vwma": True, "volume_delta": True,
            "kaufman_ama": True, "relative_volume": True, "market_structure": True,
            "dema": True, "keltner_channels": True, "roc": True,
            "candlestick_patterns": True, "fibonacci_pivot_points": True,
        },
        "weight_sets": {"default_scalping": {
            "ema_alignment": 0.22, "sma_trend_filter": 0.28, "momentum_rsi_stoch_cci_wr_mfi": 0.18,
            "bollinger_bands": 0.22, "vwap": 0.22, "psar": 0.22,
            "orderbook_imbalance": 0.07, "fibonacci_levels": 0.05,
            "ehlers_supertrend_alignment": 0.55, "macd_alignment": 0.28, "adx_strength": 0.18,
            "ichimoku_confluence": 0.38, "obv_momentum": 0.18, "cmf_flow": 0.12,
            "volatility_index_signal": 0.15, "vwma_cross": 0.15, "volume_delta_signal": 0.10,
            "kaufman_ama_cross": 0.20, "relative_volume_confirmation": 0.10, "market_structure_confluence": 0.25,
            "dema_crossover": 0.18, "keltner_breakout": 0.20, "roc_signal": 0.12,
            "candlestick_confirmation": 0.15, "fibonacci_pivot_points_confluence": 0.20,
        }},
        "indicator_settings": {
            "atr_period": 14, "ema_short_period": 9, "ema_long_period": 21,
            "rsi_period": 14, "stoch_rsi_period": 14, "stoch_k_period": 3, "stoch_d_period": 3,
            "bollinger_bands_period": 20, "bollinger_bands_std_dev": 2.0, "cci_period": 20,
            "williams_r_period": 14, "mfi_period": 14, "psar_acceleration": 0.02, "psar_max_acceleration": 0.2,
            "sma_short_period": 10, "sma_long_period": 50, "fibonacci_window": 60,
            "ehlers_fast_period": 10, "ehlers_fast_multiplier": 2.0, "ehlers_slow_period": 20, "ehlers_slow_multiplier": 3.0,
            "macd_fast_period": 12, "macd_slow_period": 26, "macd_signal_period": 9,
            "adx_period": 14, "ichimoku_tenkan_period": 9, "ichimoku_kijun_period": 26, "ichimoku_senkou_span_b_period": 52, "ichimoku_chikou_span_offset": 26,
            "obv_ema_period": 20, "cmf_period": 20, "rsi_oversold": 30, "rsi_overbought": 70,
            "stoch_rsi_oversold": 20, "stoch_rsi_overbought": 80, "cci_oversold": -100, "cci_overbought": 100,
            "williams_r_oversold": -80, "williams_r_overbought": -20, "mfi_oversold": 20, "mfi_overbought": 80,
            "volatility_index_period": 20, "vwma_period": 20, "volume_delta_period": 5, "volume_delta_threshold": 0.2,
            "kama_period": 10, "kama_fast_period": 2, "kama_slow_period": 30,
            "relative_volume_period": 20, "relative_volume_threshold": 1.5, "market_structure_lookback_period": 20,
            "dema_period": 14, "keltner_period": 20, "keltner_atr_multiplier": 2.0, "roc_period": 12, "roc_oversold": -5.0, "roc_overbought": 5.0,
            "min_candlestick_patterns_bars": 2,
        }
    }
    return cfg

@pytest.fixture
def indicator_calculator(mock_logger):
    return IndicatorCalculator(mock_logger)

@pytest.fixture
def trading_analyzer(mock_config, mock_logger, indicator_calculator):
    return TradingAnalyzer(mock_config.get_config(), mock_logger, mock_config.symbol, indicator_calculator)

@pytest.fixture
def mock_orderbook_manager():
    manager = AsyncMock(spec=AdvancedOrderbookManager)
    manager.get_depth.return_value = ([], []) # Default empty orderbook
    return manager

@pytest.fixture
def sample_df_for_analyzer():
    # Create a DataFrame with enough data points for all indicators
    # Need at least 52 + 26 = 78 bars for Ichimoku, and 2*20 = 40 for ADX
    # Let's create 100 bars
    data = {
        'open': np.random.rand(100) * 100 + 1000,
        'high': np.random.rand(100) * 100 + 1050,
        'low': np.random.rand(100) * 100 + 950,
        'close': np.random.rand(100) * 100 + 1000,
        'volume': np.random.rand(100) * 1000 + 10000,
        'turnover': np.random.rand(100) * 100000 + 1000000,
    }
    df = pd.DataFrame(data, index=pd.to_datetime(pd.date_range(start='2023-01-01', periods=100, freq='H')))
    return df

@pytest.mark.asyncio
async def test_generate_trading_signal_hold(trading_analyzer, mock_orderbook_manager, sample_df_for_analyzer):
    trading_analyzer.update_data(sample_df_for_analyzer)
    
    # Manipulate indicator values to ensure a HOLD signal
    trading_analyzer.indicator_values = {
        "EMA_Short": Decimal("100"), "EMA_Long": Decimal("100"),
        "SMA_Long": Decimal("100"),
        "RSI": 50, "StochRSI_K": 50, "StochRSI_D": 50, "CCI": 0, "WR": -50, "MFI": 50,
        "BB_Upper": Decimal("100"), "BB_Lower": Decimal("100"),
        "VWAP": Decimal("100"), "PSAR_Val": Decimal("100"), "PSAR_Dir": 0,
        "ST_Fast_Dir": 0, "ST_Slow_Dir": 0,
        "MACD_Line": 0, "MACD_Signal": 0, "MACD_Hist": 0,
        "ADX": 15, "PlusDI": 20, "MinusDI": 20,
        "Tenkan_Sen": Decimal("100"), "Kijun_Sen": Decimal("100"), "Senkou_Span_A": Decimal("100"), "Senkou_Span_B": Decimal("100"), "Chikou_Span": Decimal("100"),
        "OBV": Decimal("0"), "OBV_EMA": Decimal("0"), "CMF": Decimal("0"),
        "Volatility_Index": 0.01, "VWMA": Decimal("100"), "Volume_Delta": 0.0,
        "Kaufman_AMA": Decimal("100"), "Relative_Volume": 1.0, "Market_Structure_Trend": "SIDEWAYS",
        "DEMA": Decimal("100"), "Keltner_Upper": Decimal("100"), "Keltner_Lower": Decimal("100"),
        "ROC": 0.0, "Candlestick_Pattern": "No Pattern",
        "Pivot": Decimal("100"), "R1": Decimal("100"), "R2": Decimal("100"), "S1": Decimal("100"), "S2": Decimal("100"),
        "Support_Level": Decimal("100"), "Resistance_Level": Decimal("100"),
    }
    
    signal, score, breakdown = await trading_analyzer.generate_trading_signal(
        Decimal("1000"), mock_orderbook_manager, {}
    )
    assert signal == "HOLD"
    assert score == pytest.approx(0.0, abs=0.1) # Score should be near zero

@pytest.mark.asyncio
async def test_generate_trading_signal_buy(trading_analyzer, mock_orderbook_manager, sample_df_for_analyzer):
    trading_analyzer.update_data(sample_df_for_analyzer)
    
    # Manipulate indicator values to ensure a BUY signal
    trading_analyzer.indicator_values = {
        "EMA_Short": Decimal("105"), "EMA_Long": Decimal("100"),
        "SMA_Long": Decimal("100"),
        "RSI": 30, "StochRSI_K": 20, "StochRSI_D": 15, "CCI": -150, "WR": -90, "MFI": 10,
        "BB_Upper": Decimal("110"), "BB_Middle": Decimal("100"), "BB_Lower": Decimal("90"),
        "VWAP": Decimal("95"), "PSAR_Val": Decimal("90"), "PSAR_Dir": 1,
        "ST_Fast_Dir": 1, "ST_Slow_Dir": 1,
        "MACD_Line": 1, "MACD_Signal": 0, "MACD_Hist": 1,
        "ADX": 30, "PlusDI": 40, "MinusDI": 10,
        "Tenkan_Sen": Decimal("105"), "Kijun_Sen": Decimal("100"), "Senkou_Span_A": Decimal("105"), "Senkou_Span_B": Decimal("100"), "Chikou_Span": Decimal("105"),
        "OBV": Decimal("100"), "OBV_EMA": Decimal("90"), "CMF": Decimal("0.5"),
        "Volatility_Index": 0.015, "VWMA": Decimal("98"), "Volume_Delta": 0.5,
        "Kaufman_AMA": Decimal("99"), "Relative_Volume": 2.0, "Market_Structure_Trend": "UP",
        "DEMA": Decimal("101"), "Keltner_Upper": Decimal("105"), "Keltner_Middle": Decimal("100"), "Keltner_Lower": Decimal("95"),
        "ROC": -10.0, "Candlestick_Pattern": "Bullish Engulfing",
        "Pivot": Decimal("100"), "R1": Decimal("105"), "R2": Decimal("110"), "S1": Decimal("95"), "S2": Decimal("90"),
        "Support_Level": Decimal("99"), "Resistance_Level": Decimal("105"),
    }
    # Ensure current_close and prev_close are set for crossovers
    trading_analyzer.df.loc[trading_analyzer.df.index[-1], 'close'] = Decimal("102")
    trading_analyzer.df.loc[trading_analyzer.df.index[-2], 'close'] = Decimal("98")

    # Mock orderbook for imbalance
    mock_orderbook_manager.get_depth.return_value = (
        [PriceLevel(price=100.0, quantity=100.0, timestamp=1), PriceLevel(price=99.0, quantity=50.0, timestamp=1)],
        [PriceLevel(price=101.0, quantity=10.0, timestamp=1), PriceLevel(price=102.0, quantity=5.0, timestamp=1)]
    )

    signal, score, breakdown = await trading_analyzer.generate_trading_signal(
        Decimal("102"), mock_orderbook_manager, {}
    )
    assert signal == "BUY"
    assert score > trading_analyzer.config.signal_score_threshold

@pytest.mark.asyncio
async def test_generate_trading_signal_sell(trading_analyzer, mock_orderbook_manager, sample_df_for_analyzer):
    trading_analyzer.update_data(sample_df_for_analyzer)
    
    # Manipulate indicator values to ensure a SELL signal
    trading_analyzer.indicator_values = {
        "EMA_Short": Decimal("95"), "EMA_Long": Decimal("100"),
        "SMA_Long": Decimal("100"),
        "RSI": 70, "StochRSI_K": 80, "StochRSI_D": 85, "CCI": 150, "WR": -10, "MFI": 90,
        "BB_Upper": Decimal("110"), "BB_Middle": Decimal("100"), "BB_Lower": Decimal("90"),
        "VWAP": Decimal("105"), "PSAR_Val": Decimal("110"), "PSAR_Dir": -1,
        "ST_Fast_Dir": -1, "ST_Slow_Dir": -1,
        "MACD_Line": -1, "MACD_Signal": 0, "MACD_Hist": -1,
        "ADX": 30, "PlusDI": 10, "MinusDI": 40,
        "Tenkan_Sen": Decimal("95"), "Kijun_Sen": Decimal("100"), "Senkou_Span_A": Decimal("95"), "Senkou_Span_B": Decimal("100"), "Chikou_Span": Decimal("95"),
        "OBV": Decimal("90"), "OBV_EMA": Decimal("100"), "CMF": Decimal("-0.5"),
        "Volatility_Index": 0.015, "VWMA": Decimal("102"), "Volume_Delta": -0.5,
        "Kaufman_AMA": Decimal("101"), "Relative_Volume": 0.5, "Market_Structure_Trend": "DOWN",
        "DEMA": Decimal("99"), "Keltner_Upper": Decimal("105"), "Keltner_Middle": Decimal("100"), "Keltner_Lower": Decimal("95"),
        "ROC": 10.0, "Candlestick_Pattern": "Bearish Engulfing",
        "Pivot": Decimal("100"), "R1": Decimal("105"), "R2": Decimal("110"), "S1": Decimal("95"), "S2": Decimal("90"),
        "Support_Level": Decimal("99"), "Resistance_Level": Decimal("105"),
    }
    # Ensure current_close and prev_close are set for crossovers
    trading_analyzer.df.loc[trading_analyzer.df.index[-1], 'close'] = Decimal("98")
    trading_analyzer.df.loc[trading_analyzer.df.index[-2], 'close'] = Decimal("102")

    # Mock orderbook for imbalance
    mock_orderbook_manager.get_depth.return_value = (
        [PriceLevel(price=100.0, quantity=10.0, timestamp=1), PriceLevel(price=99.0, quantity=5.0, timestamp=1)],
        [PriceLevel(price=101.0, quantity=100.0, timestamp=1), PriceLevel(price=102.0, quantity=50.0, timestamp=1)]
    )

    signal, score, breakdown = await trading_analyzer.generate_trading_signal(
        Decimal("98"), mock_orderbook_manager, {}
    )
    assert signal == "SELL"
    assert score < -trading_analyzer.config.signal_score_threshold

@pytest.mark.asyncio
async def test_calculate_entry_tp_sl(trading_analyzer, mock_config):
    # Mock precision_manager on indicator_calculator
    trading_analyzer.indicator_calculator.round_price = MagicMock(side_effect=lambda price, sym: price.quantize(Decimal("0.01")))

    current_price = Decimal("40000")
    atr_value = Decimal("100")
    
    # Test Buy signal
    tp_buy, sl_buy = trading_analyzer.calculate_entry_tp_sl(
        current_price, atr_value, "Buy", trading_analyzer.indicator_calculator
    )
    assert tp_buy == Decimal("40200.00") # 40000 + 100 * 2.0
    assert sl_buy == Decimal("39850.00") # 40000 - 100 * 1.5

    # Test Sell signal
    tp_sell, sl_sell = trading_analyzer.calculate_entry_tp_sl(
        current_price, atr_value, "Sell", trading_analyzer.indicator_calculator
    )
    assert tp_sell == Decimal("39800.00") # 40000 - 100 * 2.0
    assert sl_sell == Decimal("40150.00") # 40000 + 100 * 1.5
