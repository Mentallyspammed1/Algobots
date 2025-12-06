"Python port of the `LeviathanEngine` class from `aimm.cjs`.
This is the core orchestrator of the trading bot, rewritten in an asynchronous,
typed, and structured manner.
"
import os
import asyncio
import logging
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional

from pybit.v5.http import HTTP
from pybit.v5.websocket import Websocket

from .oracle import OracleBrain
from .orderbook import LocalOrderBook

# Basic Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

class LeviathanEngine:
        def __init__(self):
                # --- Configuration ---
                self.config = {
                        "symbol": os.getenv("TRADE_SYMBOL", "BTCUSDT"),
                        "interval": os.getenv("TRADE_TIMEFRAME", "15"),
                        "risk_per_trade": float(os.getenv("RISK_PER_TRADE", 0.01)),
                        "leverage": os.getenv("MAX_LEVERAGE", "5"),
                        "testnet": os.getenv("BYBIT_TESTNET", "true").lower() == "true",
                        "tick_size": Decimal(os.getenv("TICK_SIZE", "0.10")),
                }

                # --- Components ---
                self.oracle = OracleBrain()
                self.book = LocalOrderBook()
                
                # --- Bybit Clients ---
                self.session = HTTP(
                        testnet=self.config["testnet"],
                        api_key=os.getenv("BYBIT_API_KEY"),
                        api_secret=os.getenv("BYBIT_API_SECRET"),
                )
                self.ws = Websocket(
                        testnet=self.config["testnet"],
                        api_key=os.getenv("BYBIT_API_KEY"),
                        api_secret=os.getenv("BYBIT_API_SECRET"),
                        channel_type="linear",
                )

                # --- State ---
                self.state: Dict[str, Any] = {
                        "price": Decimal("0"),
                        "pnl": Decimal("0"),
                        "equity": Decimal("0"),
                        "max_equity": Decimal("0"),
                        "paused": False,
                        "consecutive_losses": 0,
                        "stats": {"trades": 0, "wins": 0, "total_pnl": Decimal("0")},
                }

        def _format_price(self, price: Decimal) -> Decimal:
                """Formats a price to the correct tick size."""
                return price.to_quantize(self.config["tick_size"], rounding=ROUND_DOWN)

        async def _calculate_risk_size(self, signal: Dict[str, Any]) -> Decimal:
                """Calculates trade quantity based on risk parameters."""
                if self.state["equity"] == 0:
                        return Decimal("0.001") # Minimum size

                risk_amount = self.state["equity"] * Decimal(self.config["risk_per_trade"])
                stop_distance = abs(Decimal(signal["sl"]) - self.state["price"])
                min_stop = self.state["price"] * Decimal("0.002")
                effective_stop = max(stop_distance, min_stop)

                if effective_stop == 0:
                        return Decimal("0")

                qty = risk_amount / effective_stop
                max_qty = (self.state["equity"] * Decimal(self.config["leverage"])) / self.state["price"]
                
                return min(qty, max_qty).to_quantize(Decimal("0.001"), rounding=ROUND_DOWN)

        async def _check_funding_safe(self, action: str) -> bool:
                """Prevents entering trades with excessively high funding rates."""
                try:
                        res = self.session.get_funding_rate_history(category="linear", symbol=self.config["symbol"], limit=1)
                        rate = float(res["result"]["list"][0]["fundingRate"])
                        if action == "BUY" and rate > 0.0005:
                                logging.warning(f"Skipping BUY due to high funding rate: {rate}")
                                return False
                        if action == "SELL" and rate < -0.0005:
                                logging.warning(f"Skipping SELL due to high negative funding rate: {rate}")
                                return False
                except Exception as e:
                        logging.error(f"Could not check funding rate: {e}")
                return True

        async def _refresh_equity(self):
                """Periodically refreshes equity and checks for max drawdown."""
                try:
                        res = self.session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
                        self.state["equity"] = Decimal(res["result"]["list"][0]["totalEquity"])
                        if self.state["equity"] > self.state["max_equity"]:
                                self.state["max_equity"] = self.state["equity"]
                        
                        # Max Drawdown Guard (10%)
                        if self.state["max_equity"] > 0 and self.state["equity"] < self.state["max_equity"] * Decimal("0.9"):
                                logging.critical("Max Drawdown (10%) Hit. Bot Paused.")
                                self.state["paused"] = True

                except Exception as e:
                        logging.error(f"Could not refresh equity: {e}")

        async def _warm_up(self):
                """Fetches initial data to warm up the oracle and order book."""
                logging.info("Warming up system...")
                await self._refresh_equity()
                logging.info(f"Initial Equity: ${self.state['equity']:.2f}")

                try:
                        # Main timeframe klines
                        res = self.session.get_kline(category="linear", symbol=self.config["symbol"], interval=self.config["interval"], limit=200)
                        candles = reversed(res["result"]["list"])
                        for k in candles:
                                self.oracle.update_kline({"open": float(k[1]), "high": float(k[2]), "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])})
                        self.state["price"] = Decimal(res["result"]["list"][0][4])

                        # MTF klines (1-minute)
                        res_fast = self.session.get_kline(category="linear", symbol=self.config["symbol"], interval="1", limit=50)
                        fast_candles = reversed(res_fast["result"]["list"])
                        for k in fast_candles:
                                self.oracle.update_mtf_kline({"open": float(k[1]), "high": float(k[2]), "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])})

                        # Order book snapshot
                        ob_res = self.session.get_orderbook(category="linear", symbol=self.config["symbol"], limit=50)
                        self.book.update(ob_res["result"], is_snapshot=True)

                        logging.info("Warm-up complete. Ready.")
                except Exception as e:
                        logging.critical(f"FATAL: Warm-up failed: {e}")
                        raise

        async def _place_iceberg_order(self, signal: Dict[str, Any], entry_price: Decimal, total_qty: Decimal):
                """Splits a large order into smaller 'iceberg' slices."""
                slices = 3
                slice_qty = (total_qty / Decimal(slices)).to_quantize(Decimal("0.001"))
                side = "Buy" if signal["action"] == "BUY" else "Sell"
                
                logging.info(f"Slicing {total_qty} into {slices} iceberg orders...")
                for i in range(slices):
                        offset = Decimal(i) * self.config["tick_size"] * Decimal("0.2")
                        slice_price = entry_price + offset if side == "Buy" else entry_price - offset
                        
                        try:
                                await self.session.submit_order(
                                        category="linear", symbol=self.config["symbol"], side=side,
                                        orderType="Limit", price=str(self._format_price(slice_price)), qty=str(slice_qty),
                                        stopLoss=str(signal["sl"]), takeProfit=str(signal["tp"]), timeInForce="PostOnly",
                                )
                                await asyncio.sleep(0.2) # Delay to mask intent
                        except Exception as e:
                                logging.error(f"Iceberg slice failed: {e}")
                                break # Stop if one slice fails
                logging.info("Iceberg orders sent.")

        async def _place_maker_order(self, signal: Dict[str, Any]):
                """Evaluates a signal and places an order if conditions are met."""
                if self.state["paused"] or self.state["consecutive_losses"] >= 3:
                        return

                if not await self._check_funding_safe(signal["action"]):
                        return
                
                qty = await self._calculate_risk_size(signal)
                if qty <= 0:
                        logging.warning("Skipping trade with zero or negative quantity.")
                        return

                logging.info(f"LEVIATHAN TRIGGER: {signal['action']} | CONF: {signal['confidence']:.0%} | QTY: {qty} | REASON: {signal['reason']}")

                try:
                        pos_res = self.session.get_positions(category="linear", symbol=self.config["symbol"])
                        if pos_res["result"]["list"] and float(pos_res["result"]["list"][0]["size"]) > 0:
                                logging.warning("Position already active. Skipping.")
                                return

                        # Aggressive entry logic based on book dynamics
                        book_analysis = self.book.get_analysis()
                        best_bid_ask = self.book.get_best_bid_ask()
                        best_bid, best_ask = Decimal(best_bid_ask['bid']), Decimal(best_bid_ask['ask'])
                        tick = self.config['tick_size']

                        if signal["action"] == 'BUY':
                                aggressive_price = best_bid + tick
                                entry_price = min(aggressive_price, best_ask - tick) if book_analysis["wall_status"] == 'ASK_WALL_BROKEN' or book_analysis["skew"] > 0.2 else best_bid
                        else: # SELL
                                aggressive_price = best_ask - tick
                                entry_price = max(aggressive_price, best_bid + tick) if book_analysis["wall_status"] == 'BID_WALL_BROKEN' or book_analysis["skew"] < -0.2 else best_ask

                        await self._place_iceberg_order(signal, entry_price, qty)

                except Exception as e:
                        logging.error(f"Execution Error: {e}")

        def _handle_message(self, msg: Dict[str, Any]):
                """Main WebSocket message handler."""
                topic = msg.get("topic", "")
                data = msg.get("data", {})

                if "kline" in topic:
                        kline_interval = topic.split('.')[1]
                        for k in data:
                                k_data = {"open": float(k["open"])
                                          , "high": float(k["high"])
                                          , "low": float(k["low"])
                                          , "close": float(k["close"])
                                          , "volume": float(k["volume"])}
                                if kline_interval == self.config["interval"]:
                                        self.state["price"] = Decimal(k_data["close"])
                                        # On candle close, trigger oracle
                                        if k.get("confirm", False):
                                                self.oracle.update_kline(k_data)
                                                asyncio.create_task(self.run_oracle_cycle())
                
                elif "orderbook" in topic:
                        self.book.update(data, is_snapshot=(msg.get("type") == "snapshot"))

                elif "execution" in topic:
                        for exec_data in data:
                                if exec_data.get("execType") == "Trade" and float(exec_data.get("closedSize", 0)) > 0:
                                        pnl = Decimal(exec_data.get("execPnl", 0))
                                        self.state["stats"]["total_pnl"] += pnl
                                        self.state["stats"]["trades"] += 1
                                        if pnl > 0:
                                                self.state["consecutive_losses"] = 0
                                                self.state["stats"]["wins"] += 1
                                                logging.info(f"WIN: PnL: +${pnl:.2f}")
                                        else:
                                                self.state["consecutive_losses"] += 1
                                                logging.error(f"LOSS: PnL: ${pnl:.2f}")
        
                elif "position" in topic:
                        for pos_data in data:
                                if pos_data.get("symbol") == self.config["symbol"]:
                                        self.state["pnl"] = Decimal(pos_data.get("unrealisedPnl", "0"))
        
        async def run_oracle_cycle(self):
                """Runs the AI decision-making process."""
                print() # Newline for clarity after candle close
                signal = await self.oracle.divine(self.book.get_analysis())
                if signal.get("action") != "HOLD":
                        await self._place_maker_order(signal)

        async def _periodic_tasks(self):
                """Runs background tasks like refreshing equity and logging stats."""
                while True:
                        await asyncio.sleep(300) # 5 minutes
                        await self._refresh_equity()
                        s = self.state["stats"]
                        wr = (s['wins'] / s['trades'] * 100) if s['trades'] > 0 else 0
                        dd = (1 - self.state['equity'] / self.state['max_equity']) * 100 if self.state['max_equity'] > 0 else 0
                        logging.info(f"STATS: Trades:{s['trades']} | Win Rate:{wr:.1f}% | PnL:${s['total_pnl']:.2f} | Drawdown:{dd:.2f}%")

        async def start(self):
                """Starts the engine, warms up, and connects to the WebSocket."""
                await self._warm_up()
                
                # Start periodic tasks in the background
                asyncio.create_task(self._periodic_tasks())

                # Subscribe to public topics
                self.ws.kline_stream(interval=self.config["interval"], symbol=self.config["symbol"], callback=self._handle_message)
                self.ws.kline_stream(interval="1", symbol=self.config["symbol"], callback=self._handle_message)
                self.ws.orderbook_stream(depth=50, symbol=self.config["symbol"], callback=self._handle_message)
                
                # Subscribe to private topics
                self.ws.execution_stream(callback=self._handle_message)
                self.ws.position_stream(callback=self._handle_message)
                
                logging.info("▓▓▓ LEVIATHAN v3.0 (PYTHON) ACTIVE ▓▓▓")
                
                # Keep the main process alive and print real-time stats
                while True:
                        m = self.book.get_analysis()
                        skew_str = f"{m['skew']:.2f}"
                        pnl_str = f"{self.state['pnl']:.2f}"
                        print(f"\r[{self.config['symbol']}] {self.state['price']:.2f} | PnL: {pnl_str} | Skew: {skew_str} | Wall: {m['wall_status']}   ", end="")
                        await asyncio.sleep(1)

if __name__ == "__main__":
        from dotenv import load_dotenv
        load_dotenv()
        
        engine = LeviathanEngine()
        try:
                asyncio.run(engine.start())
        except KeyboardInterrupt:
                logging.info("Shutting down...")
        except Exception as e:
                logging.critical(f"Engine crashed: {e}")
