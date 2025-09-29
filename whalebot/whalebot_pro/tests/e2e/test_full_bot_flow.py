import asyncio
import logging
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from whalebot_pro.api.bybit_client import BybitClient
from whalebot_pro.config import Config
from whalebot_pro.main import BybitTradingBot
from whalebot_pro.utils.utilities import InMemoryCache, KlineDataFetcher


@pytest.fixture
def mock_logger():
    return MagicMock(spec=logging.Logger)


@pytest.fixture
def mock_config():
    cfg = MagicMock(spec=Config)
    cfg.BYBIT_API_KEY = "test_key"
    cfg.BYBIT_API_SECRET = "test_secret"
    cfg.symbol = "BTCUSDT"
    cfg.interval = "15m"
    cfg.loop_delay = 1  # Short loop delay for testing
    cfg.orderbook_limit = 50
    cfg.testnet = True
    cfg.timezone = "America/Chicago"
    cfg.signal_score_threshold = 2.0
    cfg.cooldown_sec = 0  # No cooldown for testing
    cfg.hysteresis_ratio = 0.0  # No hysteresis for testing
    cfg.trade_management = {
        "enabled": True,
        "account_balance": 1000.0,
        "risk_per_trade_percent": 1.0,
        "stop_loss_atr_multiple": 1.5,
        "take_profit_atr_multiple": 2.0,
        "max_open_positions": 1,
        "slippage_percent": 0.001,
        "trading_fee_percent": 0.0005,
        "enable_trailing_stop": False,
        "break_even_atr_trigger": 0.0,
        "move_to_breakeven_atr_trigger": 0.0,
        "profit_lock_in_atr_multiple": 0.0,
        "close_on_opposite_signal": True,
        "reverse_position_on_opposite_signal": False,
    }
    cfg.mtf_analysis = {"enabled": False}
    cfg.ml_enhancement = {"sentiment_analysis_enabled": False}
    cfg.current_strategy_profile = "default_scalping"
    cfg.adaptive_strategy_enabled = False
    cfg.strategy_profiles = {
        "default_scalping": {"indicators_enabled": {}, "weights": {}}
    }
    cfg.indicator_settings = {
        "atr_period": 14,
        "ema_short_period": 9,
        "ema_long_period": 21,
        "rsi_period": 14,
        "stoch_rsi_period": 14,
        "stoch_k_period": 3,
        "stoch_d_period": 3,
        "bollinger_bands_period": 20,
        "bollinger_bands_std_dev": 2.0,
        "cci_period": 20,
        "williams_r_period": 14,
        "mfi_period": 14,
        "psar_acceleration": 0.02,
        "psar_max_acceleration": 0.2,
        "sma_short_period": 10,
        "sma_long_period": 50,
        "fibonacci_window": 60,
        "ehlers_fast_period": 10,
        "ehlers_fast_multiplier": 2.0,
        "ehlers_slow_period": 20,
        "ehlers_slow_multiplier": 3.0,
        "macd_fast_period": 12,
        "macd_slow_period": 26,
        "macd_signal_period": 9,
        "adx_period": 14,
        "ichimoku_tenkan_period": 9,
        "ichimoku_kijun_period": 26,
        "ichimoku_senkou_span_b_period": 52,
        "ichimoku_chikou_span_offset": 26,
        "obv_ema_period": 20,
        "cmf_period": 20,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "stoch_rsi_oversold": 20,
        "stoch_rsi_overbought": 80,
        "cci_oversold": -100,
        "cci_overbought": 100,
        "williams_r_oversold": -80,
        "williams_r_overbought": -20,
        "mfi_oversold": 20,
        "mfi_overbought": 80,
        "volatility_index_period": 20,
        "vwma_period": 20,
        "volume_delta_period": 5,
        "volume_delta_threshold": 0.2,
        "kama_period": 10,
        "kama_fast_period": 2,
        "kama_slow_period": 30,
        "relative_volume_period": 20,
        "relative_volume_threshold": 1.5,
        "market_structure_lookback_period": 20,
        "dema_period": 14,
        "keltner_period": 20,
        "keltner_atr_multiplier": 2.0,
        "roc_period": 12,
        "roc_oversold": -5.0,
        "roc_overbought": 5.0,
        "min_candlestick_patterns_bars": 2,
    }
    cfg.indicators = {
        "ema_alignment": True,
        "sma_trend_filter": True,
        "momentum": True,
        "bollinger_bands": True,
        "vwap": True,
        "psar": True,
        "orderbook_imbalance": True,
        "fibonacci_levels": True,
        "ehlers_supertrend": True,
        "macd": True,
        "adx": True,
        "ichimoku_cloud": True,
        "obv": True,
        "cmf": True,
        "volatility_index": True,
        "vwma": True,
        "volume_delta": True,
        "kaufman_ama": True,
        "relative_volume": True,
        "market_structure": True,
        "dema": True,
        "keltner_channels": True,
        "roc": True,
        "candlestick_patterns": True,
        "fibonacci_pivot_points": True,
    }
    cfg.active_weights = {
        "ema_alignment": 0.22,
        "sma_trend_filter": 0.28,
        "momentum_rsi_stoch_cci_wr_mfi": 0.18,
        "bollinger_bands": 0.22,
        "vwap": 0.22,
        "psar": 0.22,
        "orderbook_imbalance": 0.07,
        "fibonacci_levels": 0.05,
        "ehlers_supertrend_alignment": 0.55,
        "macd_alignment": 0.28,
        "adx_strength": 0.18,
        "ichimoku_confluence": 0.38,
        "obv_momentum": 0.18,
        "cmf_flow": 0.12,
        "volatility_index_signal": 0.15,
        "vwma_cross": 0.15,
        "volume_delta_signal": 0.10,
        "kaufman_ama_cross": 0.20,
        "relative_volume_confirmation": 0.10,
        "market_structure_confluence": 0.25,
        "dema_crossover": 0.18,
        "keltner_breakout": 0.20,
        "roc_signal": 0.12,
        "candlestick_confirmation": 0.15,
        "fibonacci_pivot_points_confluence": 0.20,
    }
    return cfg


@pytest.fixture
def mock_bybit_client(mock_config):
    client = AsyncMock(spec=BybitClient)
    client.symbol = mock_config.symbol
    client.timezone = mock_config.timezone
    client.orderbook_manager = AsyncMock()
    client.orderbook_manager.get_depth.return_value = ([], [])
    client.precision_manager = MagicMock()
    client.precision_manager.round_qty.side_effect = lambda qty, sym: qty.quantize(
        Decimal("0.001")
    )
    client.precision_manager.round_price.side_effect = (
        lambda price, sym: price.quantize(Decimal("0.01"))
    )
    client.precision_manager.get_min_qty.return_value = Decimal("0.001")
    return client


@pytest.fixture
def mock_kline_data_fetcher():
    fetcher = AsyncMock(spec=KlineDataFetcher)
    return fetcher


@pytest.fixture
def mock_in_memory_cache():
    cache = MagicMock(spec=InMemoryCache)
    cache.get.return_value = None
    return cache


@pytest.fixture
def bot(
    mock_config,
    mock_logger,
    mock_bybit_client,
    mock_kline_data_fetcher,
    mock_in_memory_cache,
):
    # Patch dependencies within the bot's __init__
    with patch("whalebot_pro.main.BybitClient", return_value=mock_bybit_client):
        with patch("whalebot_pro.main.PositionManager") as MockPositionManager:
            with patch(
                "whalebot_pro.main.PerformanceTracker"
            ) as MockPerformanceTracker:
                with patch(
                    "whalebot_pro.main.IndicatorCalculator"
                ) as MockIndicatorCalculator:
                    with patch(
                        "whalebot_pro.main.TradingAnalyzer"
                    ) as MockTradingAnalyzer:
                        with patch(
                            "whalebot_pro.main.KlineDataFetcher",
                            return_value=mock_kline_data_fetcher,
                        ):
                            with patch(
                                "whalebot_pro.main.InMemoryCache",
                                return_value=mock_in_memory_cache,
                            ):
                                # Configure mocks for objects created inside bot's __init__
                                MockPositionManager.return_value = AsyncMock()
                                MockPerformanceTracker.return_value = MagicMock()
                                MockIndicatorCalculator.return_value = MagicMock()
                                MockTradingAnalyzer.return_value = AsyncMock()
                                MockTradingAnalyzer.return_value.df = (
                                    pd.DataFrame()
                                )  # Ensure analyzer.df is not empty initially
                                MockTradingAnalyzer.return_value._get_indicator_value.return_value = Decimal(
                                    "100"
                                )  # Mock ATR
                                MockTradingAnalyzer.return_value.assess_market_conditions.return_value = {
                                    "adx_value": 30,
                                    "volatility_index_value": 0.01,
                                }
                                MockTradingAnalyzer.return_value.generate_trading_signal.return_value = (
                                    "HOLD",
                                    0.0,
                                    {},
                                )

                                b = BybitTradingBot(mock_config)
                                b.logger = mock_logger  # Override logger with mock
                                b.alert_system = AsyncMock()  # Mock alert system
                                return b


@pytest.mark.asyncio
async def test_bot_initialization(bot, mock_config, mock_bybit_client):
    # Test that __init__ calls expected initializations
    mock_bybit_client.initialize.assert_not_called()  # Called in start()
    assert isinstance(bot.position_manager, AsyncMock)
    assert isinstance(bot.performance_tracker, MagicMock)
    assert isinstance(bot.indicator_calculator, MagicMock)
    assert isinstance(bot.analyzer, AsyncMock)
    assert isinstance(bot.kline_data_fetcher, AsyncMock)
    assert isinstance(bot.kline_cache, MagicMock)


@pytest.mark.asyncio
async def test_bot_start_and_shutdown(bot, mock_bybit_client, mock_logger):
    # Mock the trading loop to run only once
    bot._trading_loop = AsyncMock()
    bot._trading_loop.side_effect = [None, asyncio.CancelledError]  # Run once then stop

    with patch("asyncio.sleep", new=AsyncMock()):  # Mock asyncio.sleep
        await bot.start()

    mock_bybit_client.initialize.assert_called_once()
    mock_bybit_client.start_public_ws.assert_called_once()
    mock_bybit_client.start_private_ws.assert_called_once()
    bot._trading_loop.assert_called_once()  # Should have run once
    mock_bybit_client.stop_ws.assert_called_once()
    mock_logger.info.assert_any_call(
        f"{bot.logger.handlers[0].formatter.NEON_GREEN}--- Whalebot Trading Bot Shut Down ---{bot.logger.handlers[0].formatter.RESET}"
    )


@pytest.mark.asyncio
async def test_trading_loop_fetch_price_failure(bot, mock_bybit_client, mock_logger):
    mock_bybit_client.fetch_current_price.return_value = None
    bot.is_running = True  # Ensure loop runs

    with patch("asyncio.sleep", new=AsyncMock()):
        await bot._trading_loop()

    mock_logger.warning.assert_called_once_with(
        f"\x1b[33mALERT: [{bot.config.symbol}] Failed to fetch current price. Skipping loop.\x1b[39m"
    )
    mock_bybit_client.fetch_current_price.assert_called_once()


@pytest.mark.asyncio
async def test_trading_loop_fetch_klines_failure(
    bot, mock_bybit_client, mock_logger, mock_kline_data_fetcher
):
    mock_bybit_client.fetch_current_price.return_value = Decimal("40000")
    mock_kline_data_fetcher.fetch_klines.return_value = pd.DataFrame()  # Empty DF
    bot.is_running = True

    with patch("asyncio.sleep", new=AsyncMock()):
        await bot._trading_loop()

    mock_logger.warning.assert_called_once_with(
        f"\x1b[33mALERT: [{bot.config.symbol}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.\x1b[39m"
    )
    mock_kline_data_fetcher.fetch_klines.assert_called_once()


@pytest.mark.asyncio
async def test_trading_loop_buy_signal_open_position(
    bot, mock_bybit_client, mock_logger, mock_kline_data_fetcher, mock_in_memory_cache
):
    # Setup mocks for a BUY signal scenario
    mock_bybit_client.fetch_current_price.return_value = Decimal("40000")
    mock_kline_data_fetcher.fetch_klines.return_value = pd.DataFrame(
        {
            "open": [1000],
            "high": [1000],
            "low": [1000],
            "close": [1000],
            "volume": [100],
        },
        index=pd.to_datetime(["2023-01-01"]),
    )

    bot.analyzer.df = pd.DataFrame(
        {
            "open": [1000],
            "high": [1000],
            "low": [1000],
            "close": [1000],
            "volume": [100],
        },
        index=pd.to_datetime(["2023-01-01"]),
    )
    bot.analyzer.generate_trading_signal.return_value = ("BUY", 3.0, {})
    bot.position_manager.get_open_positions.return_value = []  # No open positions
    bot.position_manager.open_position.return_value = {}  # Simulate successful open

    bot.is_running = True

    with patch("asyncio.sleep", new=AsyncMock()):
        await bot._trading_loop()

    bot.analyzer.generate_trading_signal.assert_called_once()
    bot.position_manager.open_position.assert_called_once_with(
        "Buy", Decimal("40000"), Decimal("100")
    )
    mock_logger.info.assert_any_call(
        f"\x1b[32m[{bot.config.symbol}] Strong BUY signal detected! Score: 3.00\x1b[39m"
    )


@pytest.mark.asyncio
async def test_trading_loop_sell_signal_close_and_reverse(
    bot, mock_bybit_client, mock_logger, mock_kline_data_fetcher, mock_in_memory_cache
):
    # Setup mocks for a SELL signal scenario with existing BUY position and reversal enabled
    bot.config.trade_management["reverse_position_on_opposite_signal"] = True
    bot.config.trade_management["close_on_opposite_signal"] = True

    mock_bybit_client.fetch_current_price.return_value = Decimal("39000")
    mock_kline_data_fetcher.fetch_klines.return_value = pd.DataFrame(
        {
            "open": [1000],
            "high": [1000],
            "low": [1000],
            "close": [1000],
            "volume": [100],
        },
        index=pd.to_datetime(["2023-01-01"]),
    )

    bot.analyzer.df = pd.DataFrame(
        {
            "open": [1000],
            "high": [1000],
            "low": [1000],
            "close": [1000],
            "volume": [100],
        },
        index=pd.to_datetime(["2023-01-01"]),
    )
    bot.analyzer.generate_trading_signal.return_value = ("SELL", -3.0, {})

    # Simulate an existing BUY position
    buy_pos = {"side": "BUY", "position_id": "123"}
    bot.position_manager.get_open_positions.return_value = [buy_pos]
    bot.position_manager.close_position.return_value = None  # Simulate successful close
    bot.position_manager.open_position.return_value = {}  # Simulate successful open

    bot.is_running = True

    with patch("asyncio.sleep", new=AsyncMock()):
        await bot._trading_loop()

    bot.analyzer.generate_trading_signal.assert_called_once()
    bot.position_manager.close_position.assert_called_once_with(
        buy_pos, Decimal("39000"), bot.performance_tracker, closed_by="OPPOSITE_SIGNAL"
    )
    bot.position_manager.open_position.assert_called_once_with(
        "Sell", Decimal("39000"), Decimal("100")
    )
    mock_logger.info.assert_any_call(
        f"\x1b[91m[{bot.config.symbol}] Strong SELL signal detected! Score: -3.00\x1b[39m"
    )
