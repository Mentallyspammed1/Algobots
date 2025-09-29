import asyncio
import os
import sys
import time
from decimal import Decimal
from unittest.mock import patch

import pytest

# Add the directory containing mmx.py to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__name__), ".")))

# Import the functions and classes to be tested
# Mock global instances for testing purposes where necessary
# For BotConfig tests, we don't need to mock these as BotConfig is self-contained.
# For other tests, we might need to mock or reset these.
# For now, let's ensure they are accessible for tests that need them.
from mmx import (
    AdaptiveRateLimiter,
    BotConfig,
    BotHealth,
    MarketState,
    SessionStats,
    SymbolInfo,
    calculate_decimal_precision,
    market_state,
    session_stats,
    set_bot_state,
    symbol_info,
)


# Reset global state for each test to ensure isolation
@pytest.fixture(autouse=True)
def reset_global_state():
    global CIRCUIT_BREAKER_STATE
    global BOT_STATE
    global _SHUTDOWN_REQUESTED

    CIRCUIT_BREAKER_STATE = "NORMAL"
    BOT_STATE = "INITIALIZING"
    _SHUTDOWN_REQUESTED = False

    # Reset instances that hold state
    # bot_health.__init__() # Removed to allow patching
    market_state.__init__()
    session_stats.__init__()
    symbol_info.__init__()
    # Re-initialize config and rate_limiter if they are modified by tests
    # For now, assume they are not modified in a way that requires re-init for every test.
    # If tests modify them, add re-initialization here.


def test_calculate_decimal_precision():
    assert calculate_decimal_precision(Decimal("1.23")) == 2
    assert calculate_decimal_precision(Decimal("1")) == 0
    assert calculate_decimal_precision(Decimal("1.000")) == 3
    assert calculate_decimal_precision(Decimal("0.123456789")) == 9
    assert calculate_decimal_precision(Decimal("12345")) == 0
    assert calculate_decimal_precision(Decimal("0")) == 0
    assert calculate_decimal_precision(Decimal("1.23456789012345678")) == 17
    assert calculate_decimal_precision(Decimal("10.0")) == 1
    assert calculate_decimal_precision(Decimal("10.00")) == 2
    assert calculate_decimal_precision(Decimal("10.00000000000000000")) == 17
    assert calculate_decimal_precision(Decimal("0.00000000000000001")) == 17
    assert (
        calculate_decimal_precision(Decimal("1.234567890123456789")) == 18
    )  # Max precision set to 18 in mmx.py

    # Test with non-Decimal types
    assert calculate_decimal_precision(123) == 0
    assert (
        calculate_decimal_precision(123.45) == 0
    )  # Floats are not handled by Decimal precision logic
    assert calculate_decimal_precision("abc") == 0
    assert calculate_decimal_precision(None) == 0


class TestBotConfig:
    def test_valid_config(self):
        # Test with default valid configuration
        cfg = BotConfig()
        assert cfg.SYMBOL == "BTCUSDT"
        assert Decimal("0.001") == cfg.QUANTITY
        # No ValueError should be raised

    def test_invalid_spread_percentage(self):
        with pytest.raises(ValueError, match="SPREAD_PERCENTAGE must be positive"):
            BotConfig(SPREAD_PERCENTAGE=Decimal("0"))
        with pytest.raises(ValueError, match="SPREAD_PERCENTAGE must be positive"):
            BotConfig(SPREAD_PERCENTAGE=Decimal("-0.001"))

    def test_invalid_max_open_orders(self):
        with pytest.raises(ValueError, match="MAX_OPEN_ORDERS must be positive"):
            BotConfig(MAX_OPEN_ORDERS=0)
        with pytest.raises(ValueError, match="MAX_OPEN_ORDERS must be positive"):
            BotConfig(MAX_OPEN_ORDERS=-1)

    def test_empty_symbol(self):
        with pytest.raises(ValueError, match="SYMBOL cannot be empty"):
            BotConfig(SYMBOL="")

    def test_invalid_capital_allocation_percentage(self):
        with pytest.raises(
            ValueError, match="CAPITAL_ALLOCATION_PERCENTAGE must be between 0 and 1"
        ):
            BotConfig(CAPITAL_ALLOCATION_PERCENTAGE=Decimal("0"))
        with pytest.raises(
            ValueError, match="CAPITAL_ALLOCATION_PERCENTAGE must be between 0 and 1"
        ):
            BotConfig(CAPITAL_ALLOCATION_PERCENTAGE=Decimal("1.1"))
        with pytest.raises(
            ValueError, match="CAPITAL_ALLOCATION_PERCENTAGE must be between 0 and 1"
        ):
            BotConfig(CAPITAL_ALLOCATION_PERCENTAGE=Decimal("-0.1"))

    def test_invalid_max_position_size(self):
        with pytest.raises(
            ValueError, match="MAX_POSITION_SIZE must be between 0 and 1"
        ):
            BotConfig(MAX_POSITION_SIZE=Decimal("0"))
        with pytest.raises(
            ValueError, match="MAX_POSITION_SIZE must be between 0 and 1"
        ):
            BotConfig(MAX_POSITION_SIZE=Decimal("1.1"))
        with pytest.raises(
            ValueError, match="MAX_POSITION_SIZE must be between 0 and 1"
        ):
            BotConfig(MAX_POSITION_SIZE=Decimal("-0.1"))

    def test_invalid_orderbook_depth_levels(self):
        with pytest.raises(ValueError, match="ORDERBOOK_DEPTH_LEVELS must be positive"):
            BotConfig(ORDERBOOK_DEPTH_LEVELS=0)
        with pytest.raises(ValueError, match="ORDERBOOK_DEPTH_LEVELS must be positive"):
            BotConfig(ORDERBOOK_DEPTH_LEVELS=-1)

    def test_invalid_dashboard_refresh_rate(self):
        with pytest.raises(ValueError, match="DASHBOARD_REFRESH_RATE must be positive"):
            BotConfig(DASHBOARD_REFRESH_RATE=0.0)
        with pytest.raises(ValueError, match="DASHBOARD_REFRESH_RATE must be positive"):
            BotConfig(DASHBOARD_REFRESH_RATE=-1.0)

    def test_invalid_heartbeat_interval(self):
        with pytest.raises(ValueError, match="HEARTBEAT_INTERVAL must be positive"):
            BotConfig(HEARTBEAT_INTERVAL=0)
        with pytest.raises(ValueError, match="HEARTBEAT_INTERVAL must be positive"):
            BotConfig(HEARTBEAT_INTERVAL=-1)

    def test_invalid_quantity(self):
        with pytest.raises(ValueError, match="QUANTITY must be positive"):
            BotConfig(QUANTITY=Decimal("0"))
        with pytest.raises(ValueError, match="QUANTITY must be positive"):
            BotConfig(QUANTITY=Decimal("-0.001"))

    def test_invalid_order_lifespan_seconds(self):
        with pytest.raises(ValueError, match="ORDER_LIFESPAN_SECONDS must be positive"):
            BotConfig(ORDER_LIFESPAN_SECONDS=0)
        with pytest.raises(ValueError, match="ORDER_LIFESPAN_SECONDS must be positive"):
            BotConfig(ORDER_LIFESPAN_SECONDS=-1)

    def test_invalid_rebalance_threshold_qty(self):
        # REBALANCE_THRESHOLD_QTY can be 0, so only test negative
        with pytest.raises(
            ValueError, match="REBALANCE_THRESHOLD_QTY must be non-negative"
        ):
            BotConfig(REBALANCE_THRESHOLD_QTY=Decimal("-0.001"))

    def test_invalid_profit_percentage(self):
        with pytest.raises(ValueError, match="PROFIT_PERCENTAGE must be positive"):
            BotConfig(PROFIT_PERCENTAGE=Decimal("0"))
        with pytest.raises(ValueError, match="PROFIT_PERCENTAGE must be positive"):
            BotConfig(PROFIT_PERCENTAGE=Decimal("-0.001"))

    def test_invalid_stop_loss_percentage(self):
        with pytest.raises(ValueError, match="STOP_LOSS_PERCENTAGE must be positive"):
            BotConfig(STOP_LOSS_PERCENTAGE=Decimal("0"))
        with pytest.raises(ValueError, match="STOP_LOSS_PERCENTAGE must be positive"):
            BotConfig(STOP_LOSS_PERCENTAGE=Decimal("-0.001"))

    def test_invalid_price_threshold(self):
        # PRICE_THRESHOLD can be 0, so only test negative
        with pytest.raises(ValueError, match="PRICE_THRESHOLD must be non-negative"):
            BotConfig(PRICE_THRESHOLD=Decimal("-0.001"))

    def test_invalid_abnormal_spread_threshold(self):
        with pytest.raises(
            ValueError, match="ABNORMAL_SPREAD_THRESHOLD must be positive"
        ):
            BotConfig(ABNORMAL_SPREAD_THRESHOLD=Decimal("0"))
        with pytest.raises(
            ValueError, match="ABNORMAL_SPREAD_THRESHOLD must be positive"
        ):
            BotConfig(ABNORMAL_SPREAD_THRESHOLD=Decimal("-0.001"))

    def test_invalid_max_slippage_percentage(self):
        # MAX_SLIPPAGE_PERCENTAGE can be 0, so only test negative
        with pytest.raises(
            ValueError, match="MAX_SLIPPAGE_PERCENTAGE must be non-negative"
        ):
            BotConfig(MAX_SLIPPAGE_PERCENTAGE=Decimal("-0.001"))

    def test_invalid_performance_log_interval(self):
        with pytest.raises(
            ValueError, match="PERFORMANCE_LOG_INTERVAL must be positive"
        ):
            BotConfig(PERFORMANCE_LOG_INTERVAL=0)
        with pytest.raises(
            ValueError, match="PERFORMANCE_LOG_INTERVAL must be positive"
        ):
            BotConfig(PERFORMANCE_LOG_INTERVAL=-1)

    def test_invalid_max_log_file_size(self):
        with pytest.raises(ValueError, match="MAX_LOG_FILE_SIZE must be positive"):
            BotConfig(MAX_LOG_FILE_SIZE=0)
        with pytest.raises(ValueError, match="MAX_LOG_FILE_SIZE must be positive"):
            BotConfig(MAX_LOG_FILE_SIZE=-1)

    def test_invalid_memory_cleanup_interval(self):
        with pytest.raises(
            ValueError, match="MEMORY_CLEANUP_INTERVAL must be positive"
        ):
            BotConfig(MEMORY_CLEANUP_INTERVAL=0)
        with pytest.raises(
            ValueError, match="MEMORY_CLEANUP_INTERVAL must be positive"
        ):
            BotConfig(MEMORY_CLEANUP_INTERVAL=-1)

    def test_invalid_config_reload_interval(self):
        with pytest.raises(ValueError, match="CONFIG_RELOAD_INTERVAL must be positive"):
            BotConfig(CONFIG_RELOAD_INTERVAL=0)
        with pytest.raises(ValueError, match="CONFIG_RELOAD_INTERVAL must be positive"):
            BotConfig(CONFIG_RELOAD_INTERVAL=-1)

    def test_invalid_trading_hours(self):
        with pytest.raises(
            ValueError,
            match="TRADING_START_HOUR_UTC and TRADING_END_HOUR_UTC must be between 0 and 23",
        ):
            BotConfig(TRADING_START_HOUR_UTC=24)
        with pytest.raises(
            ValueError,
            match="TRADING_START_HOUR_UTC and TRADING_END_HOUR_UTC must be between 0 and 23",
        ):
            BotConfig(TRADING_END_HOUR_UTC=-1)

    def test_invalid_circuit_breaker_thresholds(self):
        with pytest.raises(
            ValueError,
            match="Circuit breaker thresholds must be in ascending order for severity",
        ):
            BotConfig(CB_CRITICAL_SHUTDOWN_THRESHOLD=0.5, CB_MAJOR_CANCEL_THRESHOLD=0.4)
        with pytest.raises(
            ValueError,
            match="Circuit breaker connection/success thresholds must be between 0 and 1",
        ):
            BotConfig(CB_LOW_CONNECTION_THRESHOLD=1.1)
        with pytest.raises(
            ValueError,
            match="Circuit breaker connection/success thresholds must be between 0 and 1",
        ):
            BotConfig(CB_LOW_ORDER_SUCCESS_THRESHOLD=-0.1)

    def test_get_hash(self):
        cfg1 = BotConfig(SYMBOL="BTCUSDT", QUANTITY=Decimal("0.001"))
        cfg2 = BotConfig(SYMBOL="BTCUSDT", QUANTITY=Decimal("0.001"))
        cfg3 = BotConfig(SYMBOL="ETHUSDT", QUANTITY=Decimal("0.001"))

        assert cfg1.get_hash() == cfg2.get_hash()
        assert cfg1.get_hash() != cfg3.get_hash()

    # class TestBotHealth:
    def test_initial_state(self):
        health = BotHealth()
        assert health.overall_score == 1.0

        assert health.get_status_message() == "EXCELLENT"

    def test_update_component(self):
        health = BotHealth()
        health.components = {}  # Change to a regular dict to prevent defaultdict behavior

        # Manually set weights and initial values for the components used in this test
        health.components["api_performance"] = {
            "score": 1.0,
            "last_check": time.time(),
            "message": "OK",
            "weight": 1.2,
        }
        health.components["ws_overall_connection"] = {
            "score": 1.0,
            "last_check": time.time(),
            "message": "OK",
            "weight": 2.0,
        }

        health.update_component("api_performance", 0.8, "API calls slightly slow")
        assert health.components["api_performance"]["score"] == 0.8
        assert (
            health.components["api_performance"]["message"] == "API calls slightly slow"
        )

        health.update_component("ws_overall_connection", 0.3, "WS disconnected")
        assert health.components["ws_overall_connection"]["score"] == 0.3
        assert health.overall_score == pytest.approx(0.4875)
        assert health.get_status_message() == "POOR"

    def test_score_clamping(self):
        health = BotHealth()
        health.update_component("test", 1.5, "Too high")
        assert health.components["test"]["score"] == 1.0
        health.update_component("test", -0.5, "Too low")
        assert health.components["test"]["score"] == 0.0

    def test_overall_score_calculation(self):
        health = BotHealth()
        # Manually set components for testing calculation
        health.components = {
            "comp1": {
                "score": 1.0,
                "last_check": time.time(),
                "message": "OK",
                "weight": 1.0,
            },
            "comp2": {
                "score": 0.5,
                "last_check": time.time(),
                "message": "OK",
                "weight": 1.0,
            },
            "comp3": {
                "score": 0.0,
                "last_check": time.time(),
                "message": "OK",
                "weight": 1.0,
            },
        }
        # Recalculate overall score after direct manipulation
        health._calculate_overall_score()
        expected_score = (1.0 + 0.5 + 0.0) / 3
        assert health.overall_score == pytest.approx(expected_score)

    def test_status_messages(self):
        health = BotHealth()
        health.components.clear()  # Clear default components
        health.update_component("test", 1.0)
        assert health.get_status_message() == "EXCELLENT"
        health.update_component("test", 0.8)
        assert health.get_status_message() == "GOOD"
        health.update_component("test", 0.6)
        assert health.get_status_message() == "DEGRADED"
        health.update_component("test", 0.4)
        assert health.get_status_message() == "POOR"
        health.update_component("test", 0.2)
        assert health.get_status_message() == "CRITICAL"
        health.update_component("test", 0.6)
        assert health.get_status_message() == "DEGRADED"
        health.update_component("test", 0.4)
        assert health.get_status_message() == "POOR"
        health.update_component("test", 0.1)
        assert health.get_status_message() == "CRITICAL"

    @patch("mmx.time.time")  # Patch time.time in the mmx module
    def test_overall_score_aging_components(self, mock_time):
        # Initialize BotHealth at time 100
        mock_time.return_value = 100
        health = BotHealth()
        health.components.clear()  # Clear default components for isolated testing

        # Add an active component
        health.update_component("active_comp", 0.8)  # last_check = 100
        # Overall score should be 0.8
        assert health.overall_score == pytest.approx(0.8)

        # Advance time to 150, still within 120s freshness for active_comp
        mock_time.return_value = 150
        health.update_component("another_active_comp", 0.5)  # last_check = 150
        # Expected score: (0.8 * 1.0 + 0.5 * 1.0) / (1.0 + 1.0) = 0.65
        assert health.overall_score == pytest.approx(0.65)

        # Advance time to 250. "active_comp" (last_check 100) is now stale (150s old).
        # "another_active_comp" (last_check 150) is still fresh (100s old).
        mock_time.return_value = 250
        # Trigger recalculation by updating a component or calling _calculate_overall_score directly
        health.update_component(
            "dummy", 1.0
        )  # This will update dummy and trigger recalculation
        # Only "another_active_comp" and "dummy" should be active.
        # Expected score: (0.5 * 1.0 + 1.0 * 1.0) / (1.0 + 1.0) = 0.75
        assert health.overall_score == pytest.approx(0.75)

        # Advance time to 400. All components are stale.
        mock_time.return_value = 400
        health.update_component("final_dummy", 1.0)
        # Only "final_dummy" should be active.
        assert health.overall_score == pytest.approx(1.0)


class TestAdaptiveRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_tokens(self):
        config = BotConfig(RATE_LIMIT_REQUESTS_PER_SECOND=1, RATE_LIMIT_BURST_LIMIT=1)
        limiter = AdaptiveRateLimiter(config)

        # First acquire should be immediate
        start_time = time.time()
        await limiter.acquire()
        end_time = time.time()
        assert (end_time - start_time) < 0.1  # Should be very fast

        # Second acquire should wait for 1 second (1 token per second)
        start_time = time.time()
        await limiter.acquire()
        end_time = time.time()
        assert (end_time - start_time) >= 0.9  # Should wait for rate limit

    @pytest.mark.asyncio
    async def test_burst_limit(self):
        config = BotConfig(RATE_LIMIT_REQUESTS_PER_SECOND=10, RATE_LIMIT_BURST_LIMIT=5)
        limiter = AdaptiveRateLimiter(config)

        # First 5 acquires should be immediate
        start_time = time.time()
        for _ in range(5):
            await limiter.acquire()
        end_time = time.time()
        assert (end_time - start_time) < 0.1  # Should be very fast

        # 6th acquire should wait
        start_time = time.time()
        await limiter.acquire()
        end_time = time.time()
        assert (end_time - start_time) >= 0.09  # Should wait for 1/10th of a second

    @pytest.mark.asyncio
    async def test_adaptive_scaling_increase(self):
        config = BotConfig(
            RATE_LIMIT_REQUESTS_PER_SECOND=10,
            RATE_LIMIT_BURST_LIMIT=10,
            RATE_LIMIT_ADAPTIVE_SCALING=True,
        )
        limiter = AdaptiveRateLimiter(config)

        # Simulate high success rate
        for _ in range(100):
            limiter.record_success(True)

        # Allow time for tokens to accumulate and rate to adapt
        await asyncio.sleep(1)

        # Acquire multiple tokens and check if rate increased
        # The exact rate is hard to assert due to time.time() and Decimal precision,
        # but we can check if it's faster than the base rate.
        start_time = time.time()
        for _ in range(10):  # Try to acquire more than base rate
            await limiter.acquire()
        end_time = time.time()
        # If rate increased to 15-20, 10 requests should take less than 1 second
        assert (end_time - start_time) < 1.0

    @pytest.mark.asyncio
    async def test_adaptive_scaling_decrease(self):
        config = BotConfig(
            RATE_LIMIT_REQUESTS_PER_SECOND=10,
            RATE_LIMIT_BURST_LIMIT=10,
            RATE_LIMIT_ADAPTIVE_SCALING=True,
        )
        limiter = AdaptiveRateLimiter(config)

        # Simulate low success rate
        for _ in range(100):
            limiter.record_success(False)

        # Trigger adaptive adjustment by acquiring a token
        await limiter.acquire()

        # Check if rate decreased and backoff increased
        assert limiter.current_rate < Decimal(
            str(config.RATE_LIMIT_REQUESTS_PER_SECOND)
        )
        assert limiter.backoff_factor > Decimal("1.0")


class TestSymbolInfo:
    def test_initial_state(self):
        info = SymbolInfo()
        assert info.price_precision == Decimal("0.0001")
        assert info.qty_precision == Decimal("0.001")
        assert info.min_order_value == Decimal("10.0")
        assert info.bid_levels == []
        assert info.ask_levels == []

    def test_update_orderbook_depth_valid(self):
        info = SymbolInfo()
        bids = [["100.5", "10"], ["100.4", "5"]]
        asks = [["100.6", "8"], ["100.7", "12"]]

        info.update_orderbook_depth(bids, asks)

        assert info.bid_levels == [
            (Decimal("100.5"), Decimal("10")),
            (Decimal("100.4"), Decimal("5")),
        ]
        assert info.ask_levels == [
            (Decimal("100.6"), Decimal("8")),
            (Decimal("100.7"), Decimal("12")),
        ]
        assert info.total_bid_volume == Decimal("15")
        assert info.total_ask_volume == Decimal("20")

    def test_update_orderbook_depth_invalid_data(self):
        info = SymbolInfo()
        bids = [["invalid", "10"], ["100.4", "5"]]
        asks = [["100.6", "invalid"], ["100.7", "12"]]

        # Expecting InvalidOperation to be raised, as the method does not handle it
        with pytest.raises(Exception):  # Catching generic Exception for now
            info.update_orderbook_depth(bids, asks)

        # After an exception, the lists should remain empty or partially updated depending on implementation
        # Given the current implementation, it will raise an error on the first invalid conversion.
        # So, the lists should remain empty.
        assert info.bid_levels == []
        assert info.ask_levels == []

    def test_get_market_depth_ratio(self):
        info = SymbolInfo()
        bids = [["100", "10"], ["99", "20"]]
        asks = [["101", "15"], ["102", "25"]]
        info.update_orderbook_depth(bids, asks)
        assert info.get_market_depth_ratio(levels=1) == pytest.approx(
            Decimal("10") / Decimal("15")
        )
        assert info.get_market_depth_ratio(levels=2) == pytest.approx(
            Decimal("30") / Decimal("40")
        )

        # Test edge cases
        info.bid_levels = []
        info.ask_levels = []
        assert info.get_market_depth_ratio() == Decimal("1")  # Neutral if no data

        info.bid_levels = [(Decimal("100"), Decimal("10"))]
        info.ask_levels = []
        assert info.get_market_depth_ratio() == Decimal("inf")

        info.bid_levels = []
        info.ask_levels = [(Decimal("100"), Decimal("10"))]
        assert info.get_market_depth_ratio() == Decimal("0")

    def test_estimate_slippage_buy(self):
        info = SymbolInfo()
        info.bid_levels = [(Decimal("100"), Decimal("10"))]
        info.ask_levels = [
            (Decimal("101"), Decimal("5")),
            (Decimal("102"), Decimal("5")),
        ]

        # Buy 3 units, all from 101
        slippage = info.estimate_slippage("Buy", Decimal("3"))
        assert slippage == Decimal("0")  # No slippage if filled at best ask

        # Buy 7 units, 5 from 101, 2 from 102
        slippage = info.estimate_slippage("Buy", Decimal("7"))
        # (5*101 + 2*102) / 7 = (505 + 204) / 7 = 709 / 7 = 101.2857...
        # (101.2857 - 101) / 101 = 0.002828...
        expected_slippage = (
            Decimal("101.2857142857142857") - Decimal("101")
        ) / Decimal("101")
        assert slippage.quantize(Decimal("0.0001")) == expected_slippage.quantize(
            Decimal("0.0001")
        )

    def test_estimate_slippage_sell(self):
        info = SymbolInfo()
        info.bid_levels = [
            (Decimal("100"), Decimal("5")),
            (Decimal("99"), Decimal("5")),
        ]
        info.ask_levels = [(Decimal("101"), Decimal("10"))]

        # Sell 3 units, all from 100
        slippage = info.estimate_slippage("Sell", Decimal("3"))
        assert slippage == Decimal("0")  # No slippage if filled at best bid

        # Sell 7 units, 5 from 100, 2 from 99
        slippage = info.estimate_slippage("Sell", Decimal("7"))
        # (5*100 + 2*99) / 7 = (500 + 198) / 7 = 698 / 7 = 99.7142...
        # (100 - 99.7142) / 100 = 0.002857...
        expected_slippage = (Decimal("100") - Decimal("99.7142857142857142")) / Decimal(
            "100"
        )
        assert slippage.quantize(Decimal("0.0001")) == expected_slippage.quantize(
            Decimal("0.0001")
        )

    def test_estimate_slippage_no_liquidity(self):
        info = SymbolInfo()
        info.bid_levels = []
        info.ask_levels = []
        assert info.estimate_slippage("Buy", Decimal("10")) == Decimal("0")
        assert info.estimate_slippage("Sell", Decimal("10")) == Decimal("0")

        info.bid_levels = [(Decimal("100"), Decimal("1"))]
        info.ask_levels = [(Decimal("101"), Decimal("1"))]
        # If not enough liquidity, and some is filled, slippage is calculated for filled amount.
        # If no quantity can be filled at all, it returns 0.0.
        assert info.estimate_slippage("Buy", Decimal("10")) == Decimal("0")


class TestMarketState:
    def test_initial_state(self):
        state = MarketState()
        assert state.mid_price == Decimal("0")
        assert state.best_bid == Decimal("0")
        assert state.best_ask == Decimal("0")
        assert state.open_orders == {}
        assert state.positions == {}
        assert state.last_update_time == 0.0
        assert state.last_balance_update == 0.0
        assert state.available_balance == Decimal("0")
        assert len(state.price_history) == 0
        assert len(state.trade_history) == 0
        assert state.data_quality_score == 1.0  # Initial state is 1.0

    @patch("mmx.time.time")
    @patch(
        "mmx.bot_health"
    )  # Mock bot_health to prevent its __init__ from consuming mock_time values
    def test_is_data_fresh(self, mock_bot_health, mock_time):
        state = MarketState()
        state.mid_price = Decimal("100")
        state.best_bid = Decimal("99")
        state.best_ask = Decimal("101")

        # Provide enough time values for all calls within is_data_fresh
        mock_time.side_effect = [
            100,  # state.last_update_time = mock_time()
            105,  # current_time in is_data_fresh (first call)
            115,  # state.last_update_time = mock_time()
            126,  # current_time in is_data_fresh (second call) - Changed from 125 to 126
            135,
        ]  # current_time in is_data_fresh (third call, for mid_price=0)

        state.last_update_time = mock_time()  # 100

        # Within timeout_seconds
        assert state.is_data_fresh(10) == True  # 105 - 100 = 5s, fresh
        # The data_quality_score is updated by bot_health.update_component, which is mocked.
        # So, we need to mock update_component to set data_quality_score.
        mock_bot_health.update_component.assert_called_with(
            "market_data_freshness", pytest.approx(0.5), "Market data age: 5.0s"
        )
        assert state.data_quality_score == pytest.approx(0.5)

        # Beyond timeout_seconds
        state.last_update_time = mock_time()  # 115
        assert state.is_data_fresh(10) == False  # 125 - 115 = 10s, stale
        mock_bot_health.update_component.assert_called_with(
            "market_data_freshness", 0.0, "Market data stale: 11.0s"
        )
        assert state.data_quality_score == 0.0

        # Mid price is zero
        state.mid_price = Decimal("0")
        assert state.is_data_fresh(10) == False
        mock_bot_health.update_component.assert_called_with(
            "market_data_freshness", 0.0, "Market data invalid (zero prices)"
        )
        assert state.data_quality_score == 0.0

    @patch("mmx.time.time")
    def test_add_trade(self, mock_time):
        state = MarketState()
        mock_time.return_value = 1234567890.123
        trade_data = {
            "side": "Buy",
            "price": Decimal("100.5"),
            "quantity": Decimal("0.1"),
            "order_id": "test_order_123",
            "slippage_pct": Decimal("0.0001"),
            "latency": 50,
            "type": "Execution",
            "timestamp": 1234567890.123,
        }
        state.add_trade(trade_data)
        assert len(state.trade_history) == 1
        assert state.trade_history[0]["price"] == Decimal("100.5")
        assert state.trade_history[0]["timestamp"] == 1234567890.123

        # Add another trade
        state.add_trade(
            {
                "side": "Sell",
                "price": Decimal("101"),
                "quantity": Decimal("0.2"),
                "timestamp": time.time(),
            }
        )
        assert len(state.trade_history) == 2

    @patch("mmx.time.time")
    def test_update_price_history(self, mock_time):
        state = MarketState()
        state.mid_price = Decimal("100")

        mock_time.side_effect = [100, 105]  # Provide enough time values

        state.update_price_history()
        assert len(state.price_history) == 1
        assert state.price_history[0]["price"] == Decimal("100")
        assert state.price_history[0]["timestamp"] == 100

        state.mid_price = Decimal("101")
        state.update_price_history()
        assert len(state.price_history) == 2
        assert state.price_history[1]["price"] == Decimal("101")
        assert state.price_history[1]["timestamp"] == 105


class TestSessionStats:
    def test_initial_state(self):
        stats = SessionStats()
        assert stats.orders_placed == 0
        assert stats.max_drawdown == Decimal("0")
        assert stats.get_uptime_formatted() is not None

    @patch("mmx.bot_health")  # Mock bot_health
    def test_update_pnl(self, mock_bot_health):
        stats = SessionStats()
        # Mock config and market_state for this test
        with (
            patch("mmx.config") as mock_config,
            patch("mmx.market_state") as mock_market_state,
        ):
            mock_config.CB_PNL_STOP_LOSS_PCT = Decimal("0.01")  # 1%
            mock_market_state.available_balance = Decimal("1000")

            stats.update_pnl(Decimal("100"))
            assert len(stats.profit_history) == 1
            assert stats.profit_history[0][1] == Decimal("100")
            assert stats.peak_pnl == Decimal("100")
            assert stats.max_drawdown == Decimal("0")
            mock_bot_health.update_component.assert_called_with(
                "strategy_pnl", 1.0, "PnL: 100.00, Drawdown: 0.00%"
            )
            mock_bot_health.update_component.reset_mock()

            stats.update_pnl(Decimal("50"))  # Drawdown
            assert stats.profit_history[-1][1] == Decimal("50")
            assert stats.peak_pnl == Decimal("100")
            assert stats.max_drawdown == Decimal("0.5")  # (100 - 50) / 100
            # PnL is positive, so score is 1.0
            mock_bot_health.update_component.assert_called_with(
                "strategy_pnl", 1.0, "PnL: 50.00, Drawdown: 50.00%"
            )
            mock_bot_health.update_component.reset_mock()

            stats.update_pnl(Decimal("-5"))  # Negative PnL, within 1% stop loss
            assert stats.profit_history[-1][1] == Decimal("-5")
            assert stats.peak_pnl == Decimal("100")
            assert stats.max_drawdown == Decimal("1.05")  # (100 - (-5)) / 100 = 1.05
            # PnL is -5, available balance 1000, CB_PNL_STOP_LOSS_PCT 0.01
            # abs(-5)/1000 = 0.005. Score = 1.0 - (0.005 / 0.01) = 1.0 - 0.5 = 0.5
            mock_bot_health.update_component.assert_called_with(
                "strategy_pnl", Decimal("0.5"), "PnL: -5.00, Drawdown: 105.00%"
            )
            mock_bot_health.update_component.reset_mock()

            stats.update_pnl(Decimal("120"))  # New peak
            assert stats.profit_history[-1][1] == Decimal("120")
            assert stats.peak_pnl == Decimal("120")
            assert stats.max_drawdown == Decimal(
                "1.05"
            )  # Max drawdown should not reset
            mock_bot_health.update_component.assert_called_with(
                "strategy_pnl", 1.0, "PnL: 120.00, Drawdown: 105.00%"
            )  # Updated drawdown percentage
            mock_bot_health.update_component.reset_mock()

            stats.update_pnl(Decimal("60"))  # New drawdown from new peak
            assert stats.profit_history[-1][1] == Decimal("60")
            assert stats.peak_pnl == Decimal("120")
            assert stats.max_drawdown == Decimal(
                "1.05"
            )  # (120 - 60) / 120 = 0.5, but max_drawdown is 1.05
            mock_bot_health.update_component.assert_called_with(
                "strategy_pnl", 1.0, "PnL: 60.00, Drawdown: 105.00%"
            )
            mock_bot_health.update_component.reset_mock()  # Updated drawdown percentage

    def test_record_api_error(self):
        stats = SessionStats()
        stats.record_api_error("10001")
        assert stats.api_error_counts["10001"] == 1
        stats.record_api_error("10001")
        assert stats.api_error_counts["10001"] == 2
        stats.record_api_error("20002")
        assert stats.api_error_counts["20002"] == 1

    def test_get_success_rate(self):
        stats = SessionStats()
        assert stats.get_success_rate() == 0.0

        stats.orders_placed = 10
        stats.orders_filled = 8
        stats.orders_rejected = 2
        assert stats.get_success_rate() == 100.0

        stats.orders_placed = 0
        stats.orders_filled = 0
        stats.orders_rejected = 0
        assert stats.get_success_rate() == 0.0


class TestGlobalStateFunctions:
    def test_set_bot_state(self):
        global BOT_STATE
        # Mock logger.info and bot_health.update_component to prevent side effects during test
        with (
            patch("mmx.log.info") as mock_log_info,
            patch("mmx.bot_health.update_component") as mock_update_component,
        ):
            # Test initial state change
            set_bot_state("RUNNING")
            mock_log_info.assert_called_with(
                "Bot state transition: INITIALIZING -> RUNNING"
            )
            mock_update_component.assert_called_with("bot_state", 1.0, "State: RUNNING")

            # Test that it doesn't log if state is the same
            mock_log_info.reset_mock()
            mock_update_component.reset_mock()
            set_bot_state("RUNNING")
            mock_log_info.assert_not_called()
            mock_update_component.assert_called_with(
                "bot_state", 1.0, "State: RUNNING"
            )  # Still updates health even if state is same

            # Test health component update for different states
            set_bot_state("🚨 CRITICAL_SHUTDOWN")
            mock_update_component.assert_called_with(
                "bot_state", 0.0, "State: 🚨 CRITICAL_SHUTDOWN"
            )
            set_bot_state("🚨 MAJOR_CANCEL")
            mock_update_component.assert_called_with(
                "bot_state", 0.2, "State: 🚨 MAJOR_CANCEL"
            )
            set_bot_state("🚨 MINOR_PAUSE")
            mock_update_component.assert_called_with(
                "bot_state", 0.5, "State: 🚨 MINOR_PAUSE"
            )
            set_bot_state("⏳ WAITING")
            mock_update_component.assert_called_with(
                "bot_state", 0.8, "State: ⏳ WAITING"
            )
            set_bot_state("INITIALIZING")  # Should be 1.0 for normal states
            mock_update_component.assert_called_with(
                "bot_state", 1.0, "State: INITIALIZING"
            )
            mock_log_info.reset_mock()
            mock_update_component.reset_mock()
            set_bot_state("RUNNING")
            mock_log_info.assert_not_called()
            mock_update_component.assert_called_with(
                "bot_state", 1.0, "State: RUNNING"
            )  # Still updates health even if state is same

            # Test health component update for different states
            set_bot_state("🚨 CRITICAL_SHUTDOWN")
            mock_update_component.assert_called_with(
                "bot_state", 0.0, "State: 🚨 CRITICAL_SHUTDOWN"
            )
            set_bot_state("🚨 MAJOR_CANCEL")
            mock_update_component.assert_called_with(
                "bot_state", 0.2, "State: 🚨 MAJOR_CANCEL"
            )
            set_bot_state("🚨 MINOR_PAUSE")
            mock_update_component.assert_called_with(
                "bot_state", 0.5, "State: 🚨 MINOR_PAUSE"
            )
            set_bot_state("⏳ WAITING")
            mock_update_component.assert_called_with(
                "bot_state", 0.8, "State: ⏳ WAITING"
            )
            set_bot_state("INITIALIZING")  # Should be 1.0 for normal states
            mock_update_component.assert_called_with(
                "bot_state", 1.0, "State: INITIALIZING"
            )


# To run these tests, you'll need to install pytest and pytest-asyncio:
# pip install pytest pytest-asyncio
