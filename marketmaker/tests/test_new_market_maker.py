import unittest
from unittest.mock import MagicMock, patch
import sys
import os
from decimal import Decimal

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from market_maker import BybitRest, PublicWS, PrivateWS, Quoter, Protection, MarketMaker
from config import Config

class TestNewMarketMakerComponents(unittest.TestCase):

    def setUp(self):
        self.config = Config()
        # Mock pybit.unified_trading.HTTP and WebSocket
        self.mock_http = MagicMock()
        self.mock_websocket = MagicMock()

        # Configure mock_http methods to return successful responses
        self.mock_http.place_batch_order.return_value = {"retCode": 0, "retMsg": "SUCCESS"}
        self.mock_http.amend_batch_order.return_value = {"retCode": 0, "retMsg": "SUCCESS"}
        self.mock_http.cancel_batch_order.return_value = {"retCode": 0, "retMsg": "SUCCESS"}
        self.mock_http.set_trading_stop.return_value = {"retCode": 0, "retMsg": "SUCCESS"}
        
        # Mock get_instruments_info directly on the mock_http instance
        self.mock_http.get_instruments_info.return_value = {
            "result": {"list": [{"priceFilter": {"tickSize": "0.5"}, "lotSizeFilter": {"qtyStep": "0.001", "minNotionalValue": "10"}}]}
        }

        # Patch the HTTP and WebSocket classes in pybit.unified_trading
        patcher_http = patch('pybit.unified_trading.HTTP', return_value=self.mock_http)
        patcher_websocket = patch('pybit.unified_trading.WebSocket', return_value=self.mock_websocket)
        
        self.mock_http_class = patcher_http.start()
        self.mock_websocket_class = patcher_websocket.start()
        
        self.addCleanup(patcher_http.stop)
        self.addCleanup(patcher_websocket.stop)

        # Mock run_forever to prevent actual WebSocket connection attempts and threading issues
        self.mock_websocket.run_forever = MagicMock()

        # Initialize components with mocked dependencies AFTER patching
        self.rest = BybitRest(self.config)
        self.pub = PublicWS(self.config)
        self.prv = PrivateWS(self.config)
        self.quoter = Quoter(self.config, self.rest, self.pub, self.prv)
        self.protection = Protection(self.config, self.rest, self.prv)

        # No need to mock self.rest.load_instrument here, as it's called in BybitRest.__init__
        # and get_instruments_info is mocked on self.mock_http

        # No need to mock set_trailing and set_stop_loss on the self.rest instance
        # as we are asserting on self.mock_http.set_trading_stop directly.

    # --- Test BybitRest ---
    def test_bybit_rest_load_instrument(self):
        # Ensure load_instrument sets correct values
        self.mock_http.get_instruments_info.assert_called_once_with(
            category=self.config.CATEGORY, symbol=self.config.SYMBOL
        )
        self.assertEqual(self.rest.tick, Decimal("0.5"))
        self.assertEqual(self.rest.qty_step, Decimal("0.001"))
        self.assertEqual(self.rest.min_notional, Decimal("10"))

    def test_bybit_rest_place_batch(self):
        reqs = [{"symbol": "BTCUSDT", "side": "Buy"}]
        self.rest.place_batch(reqs)
        self.mock_http.place_batch_order.assert_called_once_with(category=self.config.CATEGORY, request=reqs)

    def test_bybit_rest_amend_batch(self):
        reqs = [{"symbol": "BTCUSDT", "orderLinkId": "test", "price": "100"}]
        self.rest.amend_batch(reqs)
        self.mock_http.amend_batch_order.assert_called_once_with(category=self.config.CATEGORY, request=reqs)

    def test_bybit_rest_cancel_batch(self):
        reqs = [{"symbol": "BTCUSDT", "orderLinkId": "test"}]
        self.rest.cancel_batch(reqs)
        self.mock_http.cancel_batch_order.assert_called_once_with(category=self.config.CATEGORY, request=reqs)

    def test_bybit_rest_set_trailing(self):
        self.rest.set_trailing(Decimal("50"), Decimal("40000"))
        self.mock_http.set_trading_stop.assert_called_once_with(
            {'category': self.config.CATEGORY, 'symbol': self.config.SYMBOL, 'tpslMode': 'Full', 'trailingStop': '50', 'positionIdx': 0, 'activePrice': '40000'}
        )

    def test_bybit_rest_set_stop_loss(self):
        self.rest.set_stop_loss(Decimal("39000"))
        self.mock_http.set_trading_stop.assert_called_once_with(
            {'category': self.config.CATEGORY, 'symbol': self.config.SYMBOL, 'tpslMode': 'Full', 'stopLoss': '39000', 'positionIdx': 0}
        )

    # --- Test PublicWS ---
    def test_public_ws_on_book(self):
        msg = {"data": {"b": [["40000", "1"]], "a": [["40001", "2"]], "ts": 1234567890}}
        self.pub.on_book(msg)
        self.assertEqual(self.pub.best_bid, Decimal("40000"))
        self.assertEqual(self.pub.best_ask, Decimal("40001"))
        self.assertEqual(self.pub.bid_sz, Decimal("1"))
        self.assertEqual(self.pub.ask_sz, Decimal("2"))

    def test_public_ws_mid(self):
        self.pub.best_bid = Decimal("40000")
        self.pub.best_ask = Decimal("40001")
        self.assertEqual(self.pub.mid(), Decimal("40000.5"))

    def test_public_ws_microprice(self):
        self.pub.best_bid = Decimal("40000")
        self.pub.best_ask = Decimal("40001")
        self.pub.bid_sz = Decimal("1")
        self.pub.ask_sz = Decimal("2")
        # (40001 * 1 + 40000 * 2) / (1 + 2) = (40001 + 80000) / 3 = 120001 / 3 = 40000.333...
        self.assertAlmostEqual(self.pub.microprice(), Decimal("40000.333333333333333333333333333"))

    # --- Test PrivateWS ---
    def test_private_ws_on_position(self):
        msg = {"data": [{"symbol": self.config.SYMBOL, "category": self.config.CATEGORY, "side": "Buy", "size": "0.01", "entryPrice": "39900", "markPrice": "40000", "stopLoss": "39500", "trailingStop": "50"}]}
        self.prv.on_position(msg)
        self.assertEqual(self.prv.position_qty, Decimal("0.01"))
        self.assertEqual(self.prv.entry_price, Decimal("39900"))
        self.assertEqual(self.prv.mark_price, Decimal("40000"))
        self.assertEqual(self.prv.stop_loss, Decimal("39500"))
        self.assertEqual(self.prv.trailing_stop, Decimal("50"))

    def test_private_ws_on_order(self):
        msg = {"data": [{"orderLinkId": "test_link", "orderId": "test_id", "symbol": self.config.SYMBOL}]}
        self.prv.on_order(msg)
        self.assertIn("test_link", self.prv.orders)
        self.assertEqual(self.prv.orders["test_link"]["orderId"], "test_id")

    # --- Test Quoter ---
    def test_quoter_compute_quotes(self):
        self.pub.microprice = MagicMock(return_value=Decimal("40000"))
        self.pub.mid = MagicMock(return_value=Decimal("40000"))
        self.pub.best_bid = Decimal("39999")
        self.pub.best_ask = Decimal("40001")
        self.rest.tick = Decimal("0.5")
        self.config.BASE_SPREAD_BPS = 20 # 0.2%
        self.config.MIN_SPREAD_TICKS = 1

        bid, ask = self.quoter.compute_quotes()
        # Expected: mid=40000, half_spread = (20/10000)*40000 = 80
        # bid = 40000 - 80 = 39920, ask = 40000 + 80 = 40080
        # After respecting top-of-book: bid=39999, ask=40001
        self.assertEqual(bid, Decimal("39999"))
        self.assertEqual(ask, Decimal("40001"))

    def test_quoter_ok_qty(self):
        self.rest.qty_step = Decimal("0.001")
        self.rest.min_notional = Decimal("10")
        self.config.MAX_NOTIONAL = Decimal("3000") # Corrected attribute name
        self.pub.mid = MagicMock(return_value=Decimal("40000"))

        # Valid quantity
        self.assertEqual(self.quoter._ok_qty(Decimal("0.001")), Decimal("0.001"))
        # Too small notional
        self.assertIsNone(self.quoter._ok_qty(Decimal("0.0001"))) # 40000 * 0.0001 = 4 < 10
        # Too large notional
        self.assertIsNone(self.quoter._ok_qty(Decimal("0.1"))) # 40000 * 0.1 = 4000 > 3000

    def test_quoter_upsert_both_place_new(self):
        self.quoter.working_bid = None
        self.quoter.working_ask = None
        self.rest.place_batch = MagicMock()
        self.rest.amend_batch = MagicMock()
        self.quoter.compute_quotes = MagicMock(return_value=(Decimal("39999"), Decimal("40001")))
        self.quoter._ok_qty = MagicMock(return_value=Decimal("0.001"))
        self.config.QUOTE_SIZE = Decimal("0.001")

        self.quoter.upsert_both()
        self.rest.place_batch.assert_called_once()
        self.rest.amend_batch.assert_not_called()
        self.assertEqual(self.quoter.working_bid, Decimal("39999"))
        self.assertEqual(self.quoter.working_ask, Decimal("40001"))

    def test_quoter_upsert_both_amend_existing(self):
        self.quoter.working_bid = Decimal("39990")
        self.quoter.working_ask = Decimal("40010")
        self.rest.place_batch = MagicMock()
        self.rest.amend_batch = MagicMock()
        self.quoter.compute_quotes = MagicMock(return_value=(Decimal("39999"), Decimal("40001")))
        self.quoter._ok_qty = MagicMock(return_value=Decimal("0.001"))
        self.config.QUOTE_SIZE = Decimal("0.001")
        self.config.REPLACE_THRESHOLD_TICKS = 1
        self.rest.tick = Decimal("0.5")

        self.quoter.upsert_both()
        self.rest.place_batch.assert_not_called()
        self.rest.amend_batch.assert_called_once()
        self.assertEqual(self.quoter.working_bid, Decimal("39999"))
        self.assertEqual(self.quoter.working_ask, Decimal("40001"))

    def test_quoter_upsert_both_no_change(self):
        self.quoter.working_bid = Decimal("39999")
        self.quoter.working_ask = Decimal("40001")
        self.rest.place_batch = MagicMock()
        self.rest.amend_batch = MagicMock()
        self.quoter.compute_quotes = MagicMock(return_value=(Decimal("39999"), Decimal("40001")))
        self.quoter._ok_qty = MagicMock(return_value=Decimal("0.001"))
        self.config.QUOTE_SIZE = Decimal("0.001")
        self.config.REPLACE_THRESHOLD_TICKS = 1
        self.rest.tick = Decimal("0.5")

        self.quoter.upsert_both()
        self.rest.place_batch.assert_not_called()
        self.rest.amend_batch.assert_not_called()

    def test_quoter_cancel_all_quotes(self):
        self.rest.cancel_batch = MagicMock()
        self.quoter.cancel_all_quotes()
        self.rest.cancel_batch.assert_called_once()

    # --- Test Protection ---
    def test_protection_step_off_mode(self):
        self.config.PROTECT_MODE = "off"
        self.protection.step()
        self.rest.set_trailing.assert_not_called()
        self.rest.set_stop_loss.assert_not_called()

    def test_protection_step_trailing_mode_long_position(self):
        self.config.PROTECT_MODE = "trailing"
        self.config.TRAILING_ACTIVATE_PROFIT_BPS = Decimal("30")
        self.config.TRAILING_DISTANCE = Decimal("50") # Corrected attribute name
        self.prv.position_qty = Decimal("0.01")
        self.prv.entry_price = Decimal("40000")
        self.prv.mark_price = Decimal("40150") # PnL > 30 bps
        self.rest.tick = Decimal("0.5")
        # self.rest.set_trailing = MagicMock() # Removed this line

        self.protection.step()
        # Expected active_px = 40000 * (1 + 30/10000) = 40000 * 1.003 = 40120
        self.rest.set_trailing.assert_called_once_with(Decimal("50"), Decimal("40120"))
        self.assertTrue(self.protection._trail_applied)

    def test_protection_step_breakeven_mode_long_position(self):
        self.config.PROTECT_MODE = "breakeven"
        self.config.BE_TRIGGER_BPS = Decimal("15")
        self.config.BE_OFFSET_TICKS = 1
        self.prv.position_qty = Decimal("0.01")
        self.prv.entry_price = Decimal("40000")
        self.prv.mark_price = Decimal("40070") # PnL > 15 bps (40070/40000 - 1)*1e4 = 17.5 bps
        self.rest.tick = Decimal("0.5")
        # self.rest.set_stop_loss = MagicMock() # Removed this line

        self.protection.step()
        # Expected be_px = 40000 + 1*0.5 = 40000.5
        self.rest.set_stop_loss.assert_called_once_with(Decimal("40000.5"))
        self.assertTrue(self.protection._be_applied)

if __name__ == '__main__':
    unittest.main()
